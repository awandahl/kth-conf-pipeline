from flask import Flask, stream_with_context, Response
import subprocess
import sys

app = Flask(__name__)

@app.route('/stream')
def stream():
    def generate():
        # Run your pipeline, stream stdout
        proc = subprocess.Popen(
            [sys.executable, 'pipeline.py'],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        for line in iter(proc.stdout.readline, ''):
            yield f"data: {line}\n\n"
    return Response(stream_with_context(generate()), mimetype='text/plain')

@app.route('/')
def index():
    return '''
    <h1>Pipeline Monitor</h1>
    <iframe src="/stream" style="width:100%; height:600px; border:none;"></iframe>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
