# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: decide.proto
# plugin: python-betterproto
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import betterproto
import grpclib

from .google import protobuf


@dataclass
class StateChange(betterproto.Message):
    """
    The payload for a requested state change to a component. Components
    mustdefine a protobuf message type for their state
    """

    state: protobuf.Any = betterproto.message_field(1)


@dataclass
class ComponentParams(betterproto.Message):
    """
    The payload for a requested change to the parameters for a
    component.Components must define a protobuf message type for their
    parameters
    """

    parameters: protobuf.Any = betterproto.message_field(1)


@dataclass
class Config(betterproto.Message):
    identifier: str = betterproto.string_field(1)


@dataclass
class Reply(betterproto.Message):
    """These are the reply types"""

    # For state_change, state_reset, lock_expt, unlock_expt: indicates the
    # request was correctly formed and was acted on
    ok: protobuf.Empty = betterproto.message_field(2, group="result")
    # indicates an error with the request, contents give the cause
    error: str = betterproto.string_field(3, group="result")
    # reply to get_parameters
    params: protobuf.Any = betterproto.message_field(19, group="result")


@dataclass
class Pub(betterproto.Message):
    """
    In ZMQ, the first frame of a PUB message is the topic. In this protocol,
    the topic is used to specify the message type, allowing receivers to filter
    what they want to see. There are three main topics: `state` for state
    changes, `error` for fatal error messages, and `log` for informative log
    messages. The same protobuf type is used for all three. For error and log
    messages, the human-readable explanation is stored in the `label` field.
    """

    time: datetime = betterproto.message_field(1)
    state: protobuf.Any = betterproto.message_field(2)


class DecideControlStub(betterproto.ServiceStub):
    async def change_state(self, *, state: Optional[protobuf.Any] = None) -> Reply:
        """request change to state of a component"""

        request = StateChange()
        if state is not None:
            request.state = state

        return await self._unary_unary(
            "/decide.DecideControl/ChangeState",
            request,
            Reply,
        )

    async def reset_state(self) -> Reply:
        """request reset to default state"""

        request = protobuf.Empty()

        return await self._unary_unary(
            "/decide.DecideControl/ResetState",
            request,
            Reply,
        )

    async def request_lock(self, *, identifier: str = "") -> Reply:
        """request lock on experiment"""

        request = Config()
        request.identifier = identifier

        return await self._unary_unary(
            "/decide.DecideControl/RequestLock",
            request,
            Reply,
        )

    async def release_lock(self) -> Reply:
        """request unlock of experiment"""

        request = protobuf.Empty()

        return await self._unary_unary(
            "/decide.DecideControl/ReleaseLock",
            request,
            Reply,
        )

    async def set_parameters(
        self, *, parameters: Optional[protobuf.Any] = None
    ) -> Reply:
        """request update to parameter values"""

        request = ComponentParams()
        if parameters is not None:
            request.parameters = parameters

        return await self._unary_unary(
            "/decide.DecideControl/SetParameters",
            request,
            Reply,
        )

    async def get_parameters(self) -> Reply:
        """request parameter values for component"""

        request = protobuf.Empty()

        return await self._unary_unary(
            "/decide.DecideControl/GetParameters",
            request,
            Reply,
        )