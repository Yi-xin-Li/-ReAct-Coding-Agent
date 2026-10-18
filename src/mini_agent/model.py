"""SDK 只负责通信；这里把第三方响应转换为自己的数据类型。"""

from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)
from pydantic import ValidationError

from mini_agent.config import Settings
from mini_agent.types import (
    Message,
    ModelEvent,
    ModelFailure,
    ModelRequest,
    ModelTurn,
    ToolCall,
    Usage,
)


class DeepSeekModel:
    def __init__(self, settings: Settings, *, client: AsyncOpenAI | None = None):
        if client is None and settings.api_key is None:
            raise ValueError("请先在本地设置 DEEPSEEK_API_KEY，不要把密钥发送到聊天中")
        self.settings = settings
        self.client = client or AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=settings.request_timeout,
            # 第一阶段关闭隐式重试，让每一次真实请求都能被解释。
            max_retries=0,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.model,
                messages=[message.to_wire() for message in request.messages],
                tools=list(request.tools),
                tool_choice="auto",
                temperature=0,
                max_tokens=self.settings.max_output_tokens,
                extra_body={"thinking": {"type": "disabled"}},
                stream=False,
            )
        except AuthenticationError as exc:
            raise ModelFailure("模型认证失败，请检查本地 Key 和服务地址") from exc
        except RateLimitError as exc:
            raise ModelFailure("模型请求被限流；第一阶段不会自动重试") from exc
        except APIConnectionError as exc:
            raise ModelFailure("无法连接模型服务，请检查网络或超时设置") from exc
        except OpenAIError as exc:
            raise ModelFailure(f"模型 API 请求失败：{type(exc).__name__}") from exc

        if not response.choices or len(response.choices) != 1:
            raise ModelFailure("模型响应缺少唯一的候选结果")
        choice = response.choices[0]
        try:
            message = Message(
                role="assistant",
                content=choice.message.content,
                tool_calls=tuple(
                    ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
                    for call in choice.message.tool_calls or []
                ),
            )
            usage = Usage(
                input_tokens=response.usage.prompt_tokens if response.usage else None,
                output_tokens=response.usage.completion_tokens if response.usage else None,
            )
            yield ModelEvent(
                kind="turn",
                turn=ModelTurn(
                    message=message,
                    finish_reason=choice.finish_reason,
                    usage=usage,
                    model=response.model,
                    response_id=response.id,
                ),
            )
        except (ValidationError, AttributeError, TypeError) as exc:
            raise ModelFailure("模型返回的数据格式不符合当前适配器约定") from exc

    async def aclose(self) -> None:
        await self.client.close()
