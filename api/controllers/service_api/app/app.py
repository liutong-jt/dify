import json

from flask import current_app
from flask_restful import fields, marshal_with, Resource, reqparse

from controllers.service_api import api
from controllers.service_api.app.error import AppUnavailableError
from controllers.service_api.wraps import validate_app_token
from extensions.ext_database import db
from models.model import App, AppModelConfig, AppMode, ApiToken
from models.tools import ApiToolProvider
from services.app_service import AppService
from models.dataset import Dataset


app_fields = {
    'id': fields.String,
    'name': fields.String,
    'mode': fields.String,
    'icon': fields.String,
    'icon_background': fields.String,
    'token': fields.String,
    'datasets': fields.List(fields.List(fields.String))
}


class AppParameterApi(Resource):
    """Resource for app variables."""

    variable_fields = {
        'key': fields.String,
        'name': fields.String,
        'description': fields.String,
        'type': fields.String,
        'default': fields.String,
        'max_length': fields.Integer,
        'options': fields.List(fields.String)
    }

    system_parameters_fields = {
        'image_file_size_limit': fields.String
    }

    parameters_fields = {
        'opening_statement': fields.String,
        'suggested_questions': fields.Raw,
        'suggested_questions_after_answer': fields.Raw,
        'speech_to_text': fields.Raw,
        'text_to_speech': fields.Raw,
        'retriever_resource': fields.Raw,
        'annotation_reply': fields.Raw,
        'more_like_this': fields.Raw,
        'user_input_form': fields.Raw,
        'sensitive_word_avoidance': fields.Raw,
        'file_upload': fields.Raw,
        'system_parameters': fields.Nested(system_parameters_fields)
    }

    @validate_app_token
    @marshal_with(parameters_fields)
    def get(self, app_model: App):
        """Retrieve app parameters."""
        if app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
            workflow = app_model.workflow
            if workflow is None:
                raise AppUnavailableError()

            features_dict = workflow.features_dict
            user_input_form = workflow.user_input_form(to_old_structure=True)
        else:
            app_model_config = app_model.app_model_config
            features_dict = app_model_config.to_dict()

            user_input_form = features_dict.get('user_input_form', [])

        return {
            'opening_statement': features_dict.get('opening_statement'),
            'suggested_questions': features_dict.get('suggested_questions', []),
            'suggested_questions_after_answer': features_dict.get('suggested_questions_after_answer',
                                                                  {"enabled": False}),
            'speech_to_text': features_dict.get('speech_to_text', {"enabled": False}),
            'text_to_speech': features_dict.get('text_to_speech', {"enabled": False}),
            'retriever_resource': features_dict.get('retriever_resource', {"enabled": False}),
            'annotation_reply': features_dict.get('annotation_reply', {"enabled": False}),
            'more_like_this': features_dict.get('more_like_this', {"enabled": False}),
            'user_input_form': user_input_form,
            'sensitive_word_avoidance': features_dict.get('sensitive_word_avoidance',
                                                          {"enabled": False, "type": "", "configs": []}),
            'file_upload': features_dict.get('file_upload', {"image": {
                                                     "enabled": False,
                                                     "number_limits": 3,
                                                     "detail": "high",
                                                     "transfer_methods": ["remote_url", "local_file"]
                                                 }}),
            'system_parameters': {
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')
            }
        }


class AppMetaApi(Resource):
    @validate_app_token
    def get(self, app_model: App):
        """Get app meta"""
        return AppService().get_app_meta(app_model)


# TODO(chiyu): add mode selection
# DONE(chiyu): added mode selection, please review
class AppListApi(Resource):
    @marshal_with(app_fields)
    def get(self):
        """Get app list"""
        parser = reqparse.RequestParser()
        parser.add_argument('mode', type=str, choices=['chat', 'workflow', 'agent-chat', 'channel', 'all', 'advance-chat'], default='all', location='args', required=False)
        args = parser.parse_args()

        # get app list, not left join now, all returned apps should contain api_token
        query = db.session.query(
            App.id,
            App.name,
            App.mode,
            App.icon,
            App.icon_background,
            ApiToken.token
        )

        filters = [
            App.is_universal == False,
            ApiToken.app_id == App.id
        ]

        if args['mode'] == 'all':
            pass
        elif args['mode'] == 'workflow':
            filters.append(App.mode.in_([AppMode.WORKFLOW.value, AppMode.COMPLETION.value]))
        elif args['mode'] == 'chat':
            filters.append(App.mode.in_([AppMode.CHAT.value]))
        elif args['mode'] == 'agent-chat':
            filters.append(App.mode == AppMode.AGENT_CHAT.value)
        elif args['mode'] == 'channel':
            filters.append(App.mode == AppMode.CHANNEL.value)
        elif args['mode'] == 'advanced-chat':
            filters.append(App.mode == AppMode.ADVANCED_CHAT.value)

        # filter
        apps = query.filter(*filters).all()

        res = []
        for app in apps:
            datasets = []
            if app.mode == AppMode.CHAT.value:
                dataset = db.session.query(AppModelConfig.dataset_configs
                                                 ).filter(app.id == AppModelConfig.app_id
                                                          ).order_by(AppModelConfig.updated_at.desc()).first()
                dataset_ids = [dataset_config['dataset']['id'] for dataset_config in json.loads(dataset.dataset_configs)['datasets']['datasets']]
                for dataset_id in dataset_ids:
                    # get dataset from dataset id
                    dataset = db.session.query(Dataset).filter(
                        Dataset.id == dataset_id
                    ).first()
                    if dataset is not None:
                        datasets.append([dataset.id, dataset.name])
            
            res.append({
                'id': app.id,
                'name': app.name,
                'mode': app.mode,
                'icon': app.icon,
                'icon_background': app.icon_background,
                'token': app.token,
                'datasets': datasets
            })

        return res


api.add_resource(AppParameterApi, '/parameters')
api.add_resource(AppMetaApi, '/meta')
api.add_resource(AppListApi, '/apps')
