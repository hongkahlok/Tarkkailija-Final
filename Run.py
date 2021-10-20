import csv
import cv2
import dlib
import time
from datetime import datetime
from itertools import zip_longest

import imutils
import numpy as np

from mylib import config
from mylib.centroidtracker import CentroidTracker
from mylib.trackableobject import TrackableObject
from video_thread import VideoThread

t0 = time.time()

status = [0, 0, 0, 0]
currentTotal = 0
totalIn = 0
totalOut = 0
threshold = False


class Video(VideoThread):
    @staticmethod
    def frames():
        # initialize the list of class labels MobileNet SSD was trained to
        # detect
        CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat",
                   "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
                   "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
                   "sofa", "train", "tvmonitor"]
        protopath = "models/MobileNetSSD_deploy.prototxt"
        modelpath = "models/MobileNetSSD_deploy.caffemodel"
        input_video = "vid/example_01.mp4"
        # load our serialized model from disk
        net = cv2.dnn.readNetFromCaffe(protopath, modelpath)
        frameCount = 0
        frameRate = 30

        print("[INFO] Starting the video..")
        vs = cv2.VideoCapture(input_video)

        # initialize the video writer (we'll instantiate later if need be)
        writer = None

        # initialize the frame dimensions (we'll set them as soon as we read
        # the first frame from the video)
        W = None
        H = None

        # instantiate our centroid tracker, then initialize a list to store
        # each of our dlib correlation trackers, followed by a dictionary to
        # map each unique object ID to a TrackableObject
        ct = CentroidTracker(maxDisappeared=40, maxDistance=50)
        trackers = []
        trackableObjects = {}

        # initialize the total number of frames processed thus far, along
        # with the total number of objects that have moved either up or down
        totalFrames = 0
        totalDown = 0
        totalUp = 0
        threshold = False
        x = []
        empty = []
        empty1 = []

        # loop over frames from the video stream
        while True:
            # grab the next frame and handle if we are reading from either
            # VideoCapture or VideoStream
            frameCount += 1
            if (frameCount + frameRate) > vs.get(cv2.CAP_PROP_FRAME_COUNT):
                frameCount = 0
                vs.set(cv2.CAP_PROP_POS_FRAMES, 0)

            frame = vs.read()
            frame = frame[1]
            # resize the frame to have a maximum width of 500 pixels (the
            # less data we have, the faster we can process it), then convert
            # the frame from BGR to RGB for dlib
            frame = imutils.resize(frame, width=500)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # if the frame dimensions are empty, set them
            if W is None or H is None:
                (H, W) = frame.shape[:2]

            # initialize the current status along with our list of bounding
            # box rectangles returned by either (1) our object detector or
            # (2) the correlation trackers
            stat = "Waiting"
            rects = []

            # check to see if we should run a more computationally expensive
            # object detection method to aid our tracker
            if totalFrames % 30 == 0:
                # set the status and initialize our new set of object trackers
                stat = "Detecting"
                trackers = []

                # convert the frame to a blob and pass the blob through the
                # network and obtain the detections
                blob = cv2.dnn.blobFromImage(frame, 0.007843, (W, H), 127.5)
                net.setInput(blob)
                detections = net.forward()

                # loop over the detections
                for i in np.arange(0, detections.shape[2]):
                    # extract the confidence (i.e., probability) associated
                    # with the prediction
                    confidence = detections[0, 0, i, 2]

                    # filter out weak detections by requiring a minimum
                    # confidence
                    if confidence > 0.4:
                        # extract the index of the class label from the
                        # detections list
                        idx = int(detections[0, 0, i, 1])

                        # if the class label is not a person, ignore it
                        if CLASSES[idx] != "person":
                            continue

                        # compute the (x, y)-coordinates of the bounding box
                        # for the object
                        box = detections[0, 0, i, 3:7] * np.array([W, H, W, H])
                        (startX, startY, endX, endY) = box.astype("int")
                        rects.append(box)
                        label = "{}: {:.2f}%".format(CLASSES[idx], confidence * 100)
                        cv2.putText(frame, label, (startX, startY), cv2.FONT_HERSHEY_PLAIN, 1.5, (0, 255, 0), 2)

                        # construct a dlib rectangle object from the bounding
                        # box coordinates and then start the dlib correlation
                        # tracker
                        tracker = dlib.correlation_tracker()
                        rect = dlib.rectangle(startX, startY, endX, endY)
                        tracker.start_track(rgb, rect)

                        # add the tracker to our list of trackers so we can
                        # utilize it during skip frames
                        trackers.append(tracker)

            # otherwise, we should utilize our object *trackers* rather than
            # object *detectors* to obtain a higher frame processing throughput
            else:
                # loop over the trackers
                for tracker in trackers:
                    # set the status of our system to be 'tracking' rather
                    # than 'waiting' or 'detecting'
                    stat = "Tracking"

                    # update the tracker and grab the updated position
                    tracker.update(rgb)
                    pos = tracker.get_position()

                    # unpack the position object
                    startX = int(pos.left())
                    startY = int(pos.top())
                    endX = int(pos.right())
                    endY = int(pos.bottom())

                    # add the bounding box coordinates to the rectangles list
                    rects.append((startX, startY, endX, endY))

            # draw a horizontal line in the center of the frame -- once an
            # object crosses this line we will determine whether they were
            # moving 'up' or 'down'
            cv2.line(frame, (0, H // 2), (W, H // 2), (0, 0, 0), 3)
            cv2.putText(frame, "-Prediction border - Entrance-", (10, H - ((i * 20) + 200)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # use the centroid tracker to associate the (1) old object
            # centroids with (2) the newly computed object centroids
            objects = ct.update(rects)

            # loop over the tracked objects
            for (objectID, centroid) in objects.items():
                # check to see if a trackable object exists for the current
                # object ID
                to = trackableObjects.get(objectID, None)

                # if there is no existing trackable object, create one
                if to is None:
                    to = TrackableObject(objectID, centroid)

                # otherwise, there is a trackable object so we can utilize it
                # to determine direction
                else:
                    # the difference between the y-coordinate of the *current*
                    # centroid and the mean of *previous* centroids will tell
                    # us in which direction the object is moving (negative for
                    # 'up' and positive for 'down')
                    y = [c[1] for c in to.centroids]
                    direction = centroid[1] - np.mean(y)
                    to.centroids.append(centroid)

                    # check to see if the object has been counted or not
                    if not to.counted:
                        # if the direction is negative (indicating the object
                        # is moving up) AND the centroid is above the center
                        # line, count the object
                        if direction < 0 and centroid[1] < H // 2:
                            totalUp += 1
                            empty.append(totalUp)
                            to.counted = True

                        # if the direction is positive (indicating the object
                        # is moving down) AND the centroid is below the
                        # center line, count the object
                        elif direction > 0 and centroid[1] > H // 2:
                            totalDown += 1
                            empty1.append(totalDown)
                            # if the people limit exceeds over threshold, send an email alert
                            if sum(x) >= config.Threshold:
                                cv2.putText(frame, "-ALERT: People limit exceeded-", (10, frame.shape[0] - 80),
                                            cv2.FONT_HERSHEY_COMPLEX, 0.5, (0, 0, 255), 2)
                                threshold = True
                            else:
                                threshold = False

                            to.counted = True
                        x = []
                        # compute the sum of total people inside
                        x.append(len(empty1) - len(empty))

                # store the trackable object in our dictionary
                trackableObjects[objectID] = to

                # draw both the ID of the object and the centroid of the
                # object on the output frame
                text = "ID {}".format(objectID)
                cv2.putText(frame, text, (centroid[0] - 10, centroid[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                cv2.circle(frame, (centroid[0], centroid[1]), 4, (255, 255, 255), -1)

            # construct a tuple of information we will be displaying on the
            info = [
                ("Exit", totalUp),
                ("Enter", totalDown),
                ("Status", stat),
            ]

            totalOut = totalUp
            totalIn = totalDown
            currentTotal = len(empty1) - len(empty)

            info2 = [
                ("Total people inside", x),
            ]

            # Display the output
            for (i, (k, v)) in enumerate(info):
                text = "{}: {}".format(k, v)
                cv2.putText(frame, text, (10, H - ((i * 20) + 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            for (i, (k, v)) in enumerate(info2):
                text = "{}: {}".format(k, v)
                cv2.putText(frame, text, (265, H - ((i * 20) + 60)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Initiate a simple log to save data at end of the day
            if config.Log:
                datetimee = [datetime.now()]
                d = [datetimee, empty1, empty, x]
                export_data = zip_longest(*d, fillvalue='')

                with open('Log.csv', 'w', newline='') as myfile:
                    wr = csv.writer(myfile, quoting=csv.QUOTE_ALL)
                    wr.writerow(("End Time", "In", "Out", "Total Inside"))
                    wr.writerows(export_data)

            status[0] = currentTotal
            status[1] = totalIn
            status[2] = totalOut
            status[3] = threshold

            yield cv2.imencode('.jpg', frame)[1].tobytes()

            # increment the total number of frames processed thus far and
            # then update the FPS counter
            totalFrames += 1

    @staticmethod
    def get_crowd_count():
        return status
