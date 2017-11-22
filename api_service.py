from flask import Flask
from flask_restful import Resource, Api

from config import Config as config

app = Flask(__name__)
api = Api(app)


class HelloWorld(Resource):
    def get(self):
        return {'hello': 'world'}

    def put(self, match_id):
        return {'match_id': match_id}


api.add_resource(HelloWorld, '/match')
if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=config.api_service_port,
            debug=config.DEBUG_MODE
            )
