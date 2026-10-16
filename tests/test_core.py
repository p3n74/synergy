import socket
import unittest

from homesynergy.edge import should_cross_back, should_cross_out, y_frac_from_quartz
from homesynergy.keys import mac_to_vk
from homesynergy.protocol import AuthError, decode_frame, encode_frame, recv_obj, send_obj
from homesynergy.session import RemotePointer
from homesynergy.win_agent import is_lan_address


class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        frame = encode_frame("token-token-token", {"t": "ping", "id": 3})
        payload_len = int.from_bytes(frame[:4], "big")
        obj = decode_frame("token-token-token", frame[4 : 4 + payload_len], frame[4 + payload_len :])
        self.assertEqual(obj["id"], 3)

    def test_bad_mac(self):
        frame = encode_frame("token-token-token", {"t": "ping"})
        payload_len = int.from_bytes(frame[:4], "big")
        with self.assertRaises(AuthError):
            decode_frame("other-token-value", frame[4 : 4 + payload_len], frame[4 + payload_len :])

    def test_socketpair(self):
        left, right = socket.socketpair()
        send_obj(left, "token-token-token", {"t": "hello", "v": 1})
        msg = recv_obj(right, "token-token-token")
        self.assertEqual(msg["t"], "hello")
        left.close()
        right.close()


class BehaviorTests(unittest.TestCase):
    def test_edge_cross(self):
        self.assertTrue(should_cross_out(1918, 4, 1920, 3))
        self.assertFalse(should_cross_out(100, 4, 1920, 3))
        self.assertFalse(should_cross_out(1919, -1, 1920, 3))
        self.assertTrue(should_cross_back(-1, -2, 0))

    def test_y_fraction_uses_top_of_quartz_display(self):
        self.assertAlmostEqual(y_frac_from_quartz(0, 0, 1000), 1.0)
        self.assertAlmostEqual(y_frac_from_quartz(1000, 0, 1000), 0.0)

    def test_remote_pointer_returns_on_left_edge(self):
        pointer = RemotePointer(0, 0, 1920, 1080)
        pointer.on_enter(0.25)
        self.assertTrue(pointer.active)
        action = pointer.on_mouse(-30, 0)
        self.assertEqual(action[0][0], "leave")
        self.assertFalse(pointer.active)

    def test_keys(self):
        self.assertEqual(mac_to_vk(0), ord("A"))
        self.assertEqual(mac_to_vk(124), 0x27)
        self.assertEqual(mac_to_vk(55, command_is_control=True), 0xA2)
        self.assertEqual(mac_to_vk(55, command_is_control=False), 0x5B)

    def test_lan_only(self):
        self.assertTrue(is_lan_address("172.20.20.241"))
        self.assertTrue(is_lan_address("192.168.1.20"))
        self.assertTrue(is_lan_address("10.0.0.4"))
        self.assertTrue(is_lan_address("127.0.0.1"))
        self.assertFalse(is_lan_address("8.8.8.8"))
        self.assertFalse(is_lan_address("not-an-ip"))


if __name__ == "__main__":
    unittest.main()
