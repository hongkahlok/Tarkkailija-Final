from waitress import serve
import app
print("Waitress WSGI Server is running!")
print("Running on http://127.0.0.1:9999")
serve(app.application, channel_timeout=4000, host='0.0.0.0', port=9999)

