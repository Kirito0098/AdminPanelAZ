from app.services.file_download import (
    DOWNLOAD_MEDIA_TYPE,
    attachment_response,
    content_disposition_attachment,
)


def test_content_disposition_includes_ascii_and_rfc5987():
    header = content_disposition_attachment("AZ-alice.ovpn")
    assert 'filename="AZ-alice.ovpn"' in header
    assert "filename*=UTF-8''AZ-alice.ovpn" in header
    assert header.startswith("attachment;")


def test_content_disposition_strips_quotes_and_encodes_unicode():
    from urllib.parse import unquote

    header = content_disposition_attachment('клиент "а".conf')
    quoted = header.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in quoted
    encoded = header.split("filename*=UTF-8''", 1)[1]
    decoded = unquote(encoded)
    assert "клиент" in decoded
    assert '"' not in decoded


def test_attachment_response_is_octet_stream_not_plain_text():
    response = attachment_response("client\n", "AZ-alice.ovpn")
    assert response.media_type == DOWNLOAD_MEDIA_TYPE
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert "AZ-alice.ovpn" in response.headers["content-disposition"]
    assert response.body == b"client\n"


def test_attachment_response_accepts_bytes():
    response = attachment_response(b"\xff\x00", "file.bin")
    assert response.body == b"\xff\x00"
    assert 'filename="file.bin"' in response.headers["content-disposition"]
