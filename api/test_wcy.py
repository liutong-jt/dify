import logging

import flask_login
from flask_restful import reqparse
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.console.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.app.wraps import get_app_model
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs import helper
from libs.helper import uuid_value
from models.model import AppMode
from services.app_generate_service import AppGenerateService


# @setup_required
# @login_required
# @account_initialization_required
@get_app_model(mode=[AppMode.CHAT, AppMode.AGENT_CHAT])
def generate(app_model):
    parser = reqparse.RequestParser()
    parser.add_argument('inputs', type=dict, required=True, location='json')
    parser.add_argument('query', type=str, required=True, location='json')
    parser.add_argument('files', type=list, required=False, location='json')
    parser.add_argument('model_config', type=dict, required=True, location='json')
    parser.add_argument('conversation_id', type=uuid_value, location='json')
    parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
    parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
    args = parser.parse_args()

    streaming = args['response_mode'] != 'blocking'
    args['auto_generate_name'] = False

    account = flask_login.current_user

    try:
        response = AppGenerateService.generate(
            app_model=app_model,
            user=account,
            args=args,
            invoke_from=InvokeFrom.DEBUGGER,
            streaming=streaming
        )

        return helper.compact_generate_response(response)
    except services.errors.conversation.ConversationNotExistsError:
        raise NotFound("Conversation Not Exists.")
    except services.errors.conversation.ConversationCompletedError:
        raise ConversationCompletedError()
    except services.errors.app_model_config.AppModelConfigBrokenError:
        logging.exception("App model config broken.")
        raise AppUnavailableError()
    except ProviderTokenNotInitError as ex:
        raise ProviderNotInitializeError(ex.description)
    except QuotaExceededError:
        raise ProviderQuotaExceededError()
    except ModelCurrentlyNotSupportError:
        raise ProviderModelCurrentlyNotSupportError()
    except InvokeError as e:
        raise CompletionRequestError(e.description)
    except ValueError as e:
        raise e
    except Exception as e:
        logging.exception("internal server error.")
        raise InternalServerError()


generate(app_id="46ed2898-0fc5-4832-86e9-21831a853151")
