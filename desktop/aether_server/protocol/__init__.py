"""AetherControl Protocol Package"""
from aether_server.protocol.messages import MsgType, ErrorCode, Capability, PROTOCOL_VERSION
from aether_server.protocol.dispatcher import Dispatcher

# Codec and FrameBuffer require msgpack — imported lazily
def _get_codec():
    from aether_server.protocol.codec import Codec, FrameBuffer, ProtocolError
    return Codec, FrameBuffer, ProtocolError

__all__ = [
    "MsgType", "ErrorCode", "Capability", "PROTOCOL_VERSION",
    "Dispatcher",
]
