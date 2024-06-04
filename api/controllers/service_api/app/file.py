import json
import uuid

from flask import request, send_file
from flask_restful import Resource, marshal_with

import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from extensions.ext_storage import storage
from fields.file_fields import file_fields
from models.dataset import Document
from models.model import App, EndUser, UploadFile
from services.file_service import FileService


class FileApi(Resource):

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM))
    @marshal_with(file_fields)
    def post(self, app_model: App, end_user: EndUser):

        file = request.files['file']

        # check file
        if 'file' not in request.files:
            raise NoFileUploadedError()

        if not file.mimetype:
            raise UnsupportedFileTypeError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        try:
            upload_file = FileService.upload_file(file, end_user)
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return upload_file, 201


class FileTemplateApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM))
    @marshal_with(file_fields)
    def post(self):

        # get file from request
        file = request.files['file']
        file_id = str(uuid.uuid4())

        # check file
        if 'file' not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        data = file.read()
        redis_client.setex(file_id, 86400, data)
        redis_client.setex(file_id + "_name", 86400, file.filename)

        return {'file_id': file_id}, 201


class DocumentApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY))
    def get(self, app_model: App, end_user: EndUser, document_id):
        doc = db.session.query(Document).filter(
            Document.id == document_id
        ).first()

        upload_id = json.loads(doc.data_source_info)["upload_file_id"]
        upload_file = db.session.query(UploadFile).filter(
            UploadFile.id == upload_id
        ).first()

        if not storage.folder or storage.folder.endswith('/'):
            file_path = storage.folder + upload_file.key
        else:
            file_path = storage.folder + '/' + upload_file.key

        try:
            return send_file(file_path, as_attachment=True, download_name=upload_file.name)
        except FileNotFoundError:
            return {'message': 'File not found'}, 404


api.add_resource(FileApi, '/files/upload')
api.add_resource(FileTemplateApi, '/files/template')
api.add_resource(DocumentApi, '/document/<string:document_id>/get_file')
