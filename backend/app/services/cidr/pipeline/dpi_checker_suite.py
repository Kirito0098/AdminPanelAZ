"""Hosts used by hyperion-cs TCP 16-20 checker (suite.v2.json)."""

# Source: https://github.com/hyperion-cs/dpi-checkers/blob/main/ru/tcp-16-20/suite.v2.json
DPI_CHECKER_SUITE = {
    "US.GH-HPRN": {"provider": "Self check", "country": "🧠", "host": "hyperion-cs.github.io"},
    "PL.AKM-01": {"provider": "Akamai", "country": "🇵🇱", "host": "www.mobil.com.se"},
    "SE.AKM-01": {"provider": "Akamai", "country": "🇸🇪", "host": "cdn.apple-mapkit.com"},
    "DE.AWS-01": {"provider": "AWS", "country": "🇩🇪", "host": "amplifon.com"},
    "US.AWS-01": {"provider": "AWS", "country": "🇺🇸", "host": "optout.aboutads.info"},
    "US.CDN77-01": {"provider": "CDN77", "country": "🇺🇸", "host": "cdn.eso.org"},
    "CA.CF-01": {"provider": "Cloudflare", "country": "🇨🇦", "host": "go.coveo.com"},
    "CA.CF-02": {"provider": "Cloudflare", "country": "🇨🇦", "host": "justice.gov"},
    "US.CF-01": {"provider": "Cloudflare", "country": "🇺🇸", "host": "img.wzstats.gg"},
    "US.CF-02": {"provider": "Cloudflare", "country": "🇺🇸", "host": "esm.sh"},
    "FR.CNTB-01": {"provider": "Contabo", "country": "🇫🇷", "host": "antoniotartaglia.it"},
    "FR.CNTB-02": {"provider": "Contabo", "country": "🇫🇷", "host": "status.moow.info"},
    "DE.DO-01": {"provider": "DigitalOcean", "country": "🇩🇪", "host": "ui-arts.com"},
    "UK.DO-01": {"provider": "DigitalOcean", "country": "🇬🇧", "host": "app.thecuriositylibrary.com"},
    "UK.DO-02": {"provider": "DigitalOcean", "country": "🇬🇧", "host": "admin.survey54.com"},
    "CA.FST-01": {"provider": "Fastly", "country": "🇨🇦", "host": "ssl.p.jwpcdn.com"},
    "US.FST-01": {"provider": "Fastly", "country": "🇺🇸", "host": "www.jetblue.com"},
    "US.FTBVM-01": {"provider": "FT/BuyVM", "country": "🇺🇸", "host": "buyvm.net"},
    "US.FTBVM-02": {"provider": "FT/BuyVM", "country": "🇺🇸", "host": "dmvideo.download"},
    "LU.GCORE-01": {"provider": "Gcore", "country": "🇱🇺", "host": "gcore.com"},
    "US.GC-01": {"provider": "Google Cloud", "country": "🇺🇸", "host": "api.usercentrics.eu"},
    "US.GC-02": {"provider": "Google Cloud", "country": "🇺🇸", "host": "widgets.reputation.com"},
    "DE.HE-01": {"provider": "Hetzner", "country": "🇩🇪", "host": "king.hr"},
    "DE.HE-02": {"provider": "Hetzner", "country": "🇩🇪", "host": "mail.server.apaone.com"},
    "FI.HE-01": {"provider": "Hetzner", "country": "🇫🇮", "host": "nioges.com"},
    "FI.HE-02": {"provider": "Hetzner", "country": "🇫🇮", "host": "5fd8bdae.nip.io"},
    "FI.HE-03": {"provider": "Hetzner", "country": "🇫🇮", "host": "net4u.de"},
    "US.MBCOM-01": {"provider": "Melbicom", "country": "🇺🇸", "host": "elecane.com"},
    "NL.MS-01": {"provider": "Microsoft/Azure", "country": "🇳🇱", "host": "store.takeda.com"},
    "ES.OR-01": {"provider": "Oracle", "country": "🇪🇸", "host": "sh00065.hostgator.com"},
    "SG.OR-01": {"provider": "Oracle", "country": "🇸🇬", "host": "ged.com.sg"},
    "FR.OVH-01": {"provider": "OVH", "country": "🇫🇷", "host": "www.adwin.fr"},
    "FR.OVH-02": {"provider": "OVH", "country": "🇫🇷", "host": "www.emca.be"},
    "NL.SW-01": {"provider": "Scaleway", "country": "🇳🇱", "host": "www.velivole.fr"},
    "DE.VLTR-01": {"provider": "Vultr", "country": "🇩🇪", "host": "askit-app.de"},
    "US.VLTR-01": {"provider": "Vultr", "country": "🇺🇸", "host": "us.rudder.qntmnet.com"},
}


def lookup_checker_node(node_id):
    key = str(node_id or "").strip().upper().lstrip("#")
    return DPI_CHECKER_SUITE.get(key)
