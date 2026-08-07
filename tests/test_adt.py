"""ADT^A03 projection: the EMS encounter as the ADT visit."""

import pytest

from emsinterop.assemble.adt import build_adt_a03
from emsinterop.convert import convert

from .conftest import CHEST_PAIN, FIXTURES

REFUSAL = FIXTURES / "pcr_refusal.xml"


def _message(path=CHEST_PAIN, **kwargs):
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    raw = build_adt_a03(result.context, **kwargs)
    return {seg.split("|", 1)[0]: seg.split("|") for seg in raw.strip("\r").split("\r")}, raw


def test_message_envelope():
    segments, raw = _message(receiving_application="ENS", receiving_facility="STATE-HIE")
    msh = segments["MSH"]
    assert msh[1] == "^~\\&"
    assert msh[2] == "emsinterop"
    assert msh[3] == "Wasatch Valley EMS (synthetic)"
    assert msh[4] == "ENS" and msh[5] == "STATE-HIE"
    assert msh[8] == "ADT^A03^ADT_A03"
    assert msh[10] == "P" and msh[11] == "2.5.1"
    assert segments["EVN"][1] == "A03"
    assert segments["EVN"][2] == "20260806094805-0600"  # transfer of care
    assert raw.endswith("\r")


def test_pid_demographics():
    segments, _ = _message()
    pid = segments["PID"]
    assert "AG-778812^^^4901^PI" in pid[3]
    assert pid[5] == "Trujillo^Elena"
    assert pid[7] == "19800214"
    assert pid[8] == "F"
    assert "1420 Cottonwood Ln" in pid[11]


def test_pv1_visit_and_transported_disposition():
    segments, _ = _message()
    pv1 = segments["PV1"]
    assert pv1[2] == "E"
    assert pv1[3] == "Medic 42"  # the unit is the visit location
    assert "PCR-2026-000123^^^4901^VN" in pv1[19]
    assert pv1[36] == "02"  # transported -> transferred to hospital (NUBC)
    assert pv1[44] == "20260806090610-0600"  # arrived at patient
    assert pv1[45] == "20260806094805-0600"  # transfer of care


def test_refusal_maps_to_ama():
    segments, _ = _message(REFUSAL)
    assert segments["PV1"][36] == "07"  # left AMA / discontinued care
    # refusal has no destination arrival: end-of-visit falls back to left-scene
    assert segments["PV1"][45] == "20260806144100-0600"


def test_dg1_impressions_pass_through():
    _, raw = _message()
    dg1 = [seg for seg in raw.split("\r") if seg.startswith("DG1")]
    assert dg1[0].split("|")[3] == "I21.9^^I10"
    assert dg1[0].split("|")[6] == "F"  # primary = final
    assert dg1[1].split("|")[3] == "I20.9^^I10"
    assert dg1[1].split("|")[6] == "W"  # secondary = working


def test_escaping_and_determinism():
    result = convert(CHEST_PAIN, agency_names={"4901": "Wasatch & Valley | EMS"})[0]
    raw = build_adt_a03(result.context)
    assert "Wasatch \\T\\ Valley \\F\\ EMS" in raw
    assert raw == build_adt_a03(result.context)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.xml")), ids=lambda p: p.stem)
def test_corpus_renders(path):
    segments, raw = _message(path)
    assert set(segments) >= {"MSH", "EVN", "PID", "PV1"}
    assert segments["PV1"][36] in {"01", "02", "07", "20"}


def test_a04_prearrival():
    from emsinterop.assemble.adt import build_adt_a04
    result = convert(CHEST_PAIN, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    raw = build_adt_a04(result.context)
    segments = {seg.split("|", 1)[0]: seg.split("|") for seg in raw.strip("\r").split("\r")}
    assert segments["MSH"][8] == "ADT^A04^ADT_A01"  # A04 uses the A01 structure
    assert segments["EVN"][1] == "A04"
    # chest-pain has prearrival alert "No" (4224001) with nil .25 -> falls back
    # to left-scene time as the registration moment
    assert segments["EVN"][2] == "20260806092200-0600"
    pv1 = segments["PV1"]
    assert pv1[36] == ""  # visit not ended: no discharge status
    assert pv1[45] == ""  # and no discharge time
    assert any(seg.startswith("DG1") for seg in raw.split("\r"))  # ED sees why


def test_mllp_transport_round_trip():
    import socket
    import threading

    from emsinterop.transport import MllpTransport

    received = {}
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        conn, _ = server.accept()
        data = b""
        while b"\x1c" not in data:
            data += conn.recv(4096)
        received["frame"] = data
        ack = b"\x0bMSH|^~\\&|ENS|HIE|||20260806||ACK^A03|X|P|2.5.1\rMSA|AA|X\r\x1c\x0d"
        conn.sendall(ack)
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    result = convert(CHEST_PAIN)[0]
    from emsinterop.assemble.adt import build_adt_a03
    receipt = MllpTransport("127.0.0.1", port, timeout=10).send(build_adt_a03(result.context))
    thread.join(timeout=10)
    server.close()

    assert receipt["status"] == "delivered" and receipt["ack_code"] == "AA"
    frame = received["frame"]
    assert frame.startswith(b"\x0bMSH|") and frame.endswith(b"\x1c\x0d")
    assert b"ADT^A03^ADT_A03" in frame


def test_policy_default_is_completed_only():
    from emsinterop.assemble.adt import build_adt_messages
    result = convert(CHEST_PAIN)[0]
    messages = build_adt_messages(result.context)
    assert [event for event, _ in messages] == ["A03"]


def test_policy_both_sends_prearrival_first():
    from emsinterop.assemble.adt import AdtConfig, build_adt_messages
    result = convert(CHEST_PAIN)[0]
    messages = build_adt_messages(result.context, AdtConfig(send_prearrival=True))
    assert [event for event, _ in messages] == ["A04", "A03"]


def test_prearrival_self_gates_without_destination():
    from emsinterop.assemble.adt import AdtConfig, build_adt_messages
    result = convert(REFUSAL)[0]  # refusal: no destination recorded
    messages = build_adt_messages(result.context, AdtConfig(send_prearrival=True))
    assert [event for event, _ in messages] == ["A03"]


def test_policy_prearrival_only():
    from emsinterop.assemble.adt import AdtConfig, build_adt_messages
    result = convert(CHEST_PAIN)[0]
    config = AdtConfig(send_completed=False, send_prearrival=True)
    assert [e for e, _ in build_adt_messages(result.context, config)] == ["A04"]
