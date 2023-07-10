# Copyright 2022-2023 XProbe Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import inspect
from typing import TYPE_CHECKING, Any, Generic, Iterator, Optional, TypeVar, Union

import xoscar as xo

if TYPE_CHECKING:
    from ..model.llm.core import Model
    from ..types import ChatCompletionChunk, CompletionChunk

import logging

logger = logging.getLogger(__name__)


T = TypeVar("T")


class IteratorWrapper(Generic[T]):
    def __init__(self, model_actor_addr: str, model_actor_uid: str):
        self._model_actor_addr = model_actor_addr
        self._model_actor_uid = model_actor_uid
        self._model_actor_ref: Optional[xo.ActorRefType["ModelActor"]] = None

    def __aiter__(self):
        return self

    async def __anext__(self) -> T:
        if self._model_actor_ref is None:
            self._model_actor_ref = await xo.actor_ref(
                address=self._model_actor_addr, uid=self._model_actor_uid
            )

        try:
            assert self._model_actor_ref is not None
            return await self._model_actor_ref.next()
        except Exception as e:
            if "StopIteration" in str(e):
                raise StopAsyncIteration
            else:
                raise


class ModelActor(xo.Actor):
    @classmethod
    def gen_uid(cls, model: "Model"):
        return f"{model.__class__}-model-actor"

    def __init__(self, model: "Model"):
        super().__init__()
        self._model = model
        self._generator: Optional[Iterator] = None

    def load(self):
        self._model.load()

    async def _wrap_generator(self, ret: Any):
        if inspect.isgenerator(ret):
            self._generator = ret
            return IteratorWrapper(
                model_actor_addr=self.address, model_actor_uid=self.uid
            )
        else:
            return ret

    async def generate(self, prompt: str, *args, **kwargs):
        logger.warning("Generate, self address: %s", self.address)

        if not hasattr(self._model, "generate"):
            raise AttributeError("generate")

        return self._wrap_generator(
            getattr(self._model, "generate")(prompt, *args, **kwargs)
        )

    async def chat(self, prompt: str, *args, **kwargs):
        if not hasattr(self._model, "chat"):
            raise AttributeError("chat")

        return self._wrap_generator(
            getattr(self._model, "chat")(prompt, *args, **kwargs)
        )

    async def next(self) -> Union["ChatCompletionChunk", "CompletionChunk"]:
        try:
            assert self._generator is not None
            return next(self._generator)
        except StopIteration:
            self._generator = None
            raise Exception("StopIteration")