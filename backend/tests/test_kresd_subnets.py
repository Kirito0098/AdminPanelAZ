"""Подсети клиентов и fake-IP: правка kresd.conf, proxy.py и services.env AZ-AWG2.

Смена ``ALTERNATIVE_CLIENT_IP`` / ``ALTERNATIVE_FAKE_IP`` в setup сама по себе ничего не
меняет в резолвере и proxy.py — если панель не перепишет файлы, клиенты получат новые
адреса, а DNS и fake-IP останутся на старых.
"""

from app.services.kresd_subnets import (
    fake_pool,
    with_awg_services_env,
    with_client_subnets,
    with_fake_cidr,
)

KRESD_CONF = """
	local antizapret_dns = 1 -- AntiZapret VPN DNS
	net.listen('127.1.1.1', 53, {kind = 'dns', freebind = true})
	view:addr('172.29.0.0/21', policy.domains(policy.ANSWER({[kres.type.A] = {rdata = kres.str2ip('172.29.0.1')}}, true), {todname(hostname())}))
	view:addr('172.29.8.0/21', policy.domains(policy.ANSWER({[kres.type.A] = {rdata = kres.str2ip('172.29.8.1')}}, true), {todname(hostname())}))
	view:addr('172.28.16.0/21', policy.domains(policy.ANSWER({[kres.type.A] = {rdata = kres.str2ip('172.28.16.1')}}, true), {todname(hostname())}))
	net.listen('127.2.2.2', 53, {kind = 'dns', freebind = true})
"""

PROXY_PY = (
    '\tp.add_argument("--fake-cidr",default="198.18.0.0/16",'
    'help="Fake IP CIDR (default: 198.18.0.0/15)")\n'
)

AWG_SERVICES_ENV = """# режим интеграции AmneziaWG
MODE=parallel
AZ_IFACE=antizapret-awg
AZ_PORT=24258
AZ_SUBNET=172.29.9
AZ_DNS=172.29.8.1
VPN_IFACE=vpn-awg
VPN_PORT=37091
VPN_SUBNET=172.28.9
VPN_DNS=172.29.8.1
MTU=1320
"""


def test_client_subnets_switch_to_10_and_back():
    switched = with_client_subnets(KRESD_CONF, alternative=False)
    assert "10.29.8.0/21" in switched
    assert "10.28.16.0/21" in switched
    assert "172.29" not in switched
    assert "172.28" not in switched
    # DNS-выбор и listen-адреса резолверов не затронуты
    assert "local antizapret_dns = 1" in switched
    assert "net.listen('127.1.1.1', 53, {kind = 'dns', freebind = true})" in switched
    assert "net.listen('127.2.2.2', 53, {kind = 'dns', freebind = true})" in switched
    # обратное переключение возвращает файл байт в байт
    assert with_client_subnets(switched, alternative=True) == KRESD_CONF


def test_client_subnets_noop_when_mode_matches():
    assert with_client_subnets(KRESD_CONF, alternative=True) == KRESD_CONF
    switched = with_client_subnets(KRESD_CONF, alternative=False)
    assert with_client_subnets(switched, alternative=False) == switched


def test_fake_cidr_follows_alternative_fake_ip():
    assert fake_pool(True) == "198.18"
    assert fake_pool(False) == "10.30"
    assert 'default="10.30.0.0/15"' in with_fake_cidr(PROXY_PY, alternative=False)
    assert 'default="198.18.0.0/15"' in with_fake_cidr(PROXY_PY, alternative=True)


def test_fake_cidr_leaves_unknown_proxy_py_untouched():
    assert with_fake_cidr("no arguments here", alternative=False) == "no arguments here"


def test_awg_services_env_subnets_switch_and_restore():
    switched = with_awg_services_env(AWG_SERVICES_ENV, alternative=False)
    assert "AZ_SUBNET=10.29.9" in switched
    assert "VPN_SUBNET=10.28.9" in switched
    assert "AZ_DNS=10.29.8.1" in switched
    assert "VPN_DNS=10.29.8.1" in switched
    assert "MTU=1320" in switched
    assert "AZ_PORT=24258" in switched
    assert with_awg_services_env(switched, alternative=True) == AWG_SERVICES_ENV
