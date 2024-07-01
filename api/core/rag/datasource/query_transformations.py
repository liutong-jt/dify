import logging

from core.model_manager import ModelManager
from core.model_runtime.entities.message_entities import UserPromptMessage
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.invoke import InvokeError


logger = logging.getLogger(__name__)

class QueryTransformationService:
    @classmethod
    def hyde(cls, tenant_id, query):
        if not tenant_id:
            return query

        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM,
        )

        prompt = f'请你认真思考后回答这个问题：{query}' # 后续把 prompt 做封装。

        prompts = [UserPromptMessage(content=prompt)]
        try:
            response = model_instance.invoke_llm(
                prompt_messages=prompts,
                model_parameters={
                    "max_tokens": 200,
                    "temperature": 1
                },
                stream=False
            )
            answer = response.message.content
            logger.info(f"HyDE response: {answer}")
        except InvokeError:
            answer = []
        except Exception as e:
            logging.exception(e)
            answer = []

        return answer