"""Networks (autonomous systems) used by VPN providers, by Tor exit relays, by
the hosting companies many VPNs rent their servers from, and by cloud and
hosting companies that known spammers' sign-ups came from.

`manage.py load_vpn_asn_rules` adds a participation-only network owner block
rule for each, which admins can then deactivate one by one if a network turns
out to block people it shouldn't.

Each network's organization is MaxMind's name for its owner, checked against
GeoLite2-ASN on 2026-10-21. The command skips networks whose owner has changed
since, because the number may now belong to someone else.

Left out on purpose:
- iCloud Private Relay (Akamai AS36183, Cloudflare AS13335 and Fastly AS54113)
  and corporate security gateways (Zscaler AS53813 and Netskope AS55256), which
  many ordinary visitors use without knowing.
- Networks on the source lists that mostly carry other traffic, such as business
  ISPs, e.g. Glesys and Kia's Slovak branch (AS212537). General hosting
  companies such as Leaseweb are only included once spammers turn up on them,
  since few real participants browse from servers.
- Home and business ISPs that spammers' sign-ups came from (e.g. Verizon,
  Charter and Level 3), which real participants use too.
"""

from typing import NamedTuple

# Where each network came from.
X4BNET = "https://github.com/X4BNet/lists_vpn"
BAD_ASN_LIST = "https://github.com/bountyyfi/bad-asn-list"
OWNER_NAME = "Searching GeoLite2-ASN for the provider's company name"
SPAM_SIGNUPS = "Known spammers' IP addresses, checked on 2026-10-21"

VPN = "VPN"
TOR = "Tor exit relays"
VPN_HOSTING = "Hosting used by VPNs"
SPAM_HOSTING = "Cloud and hosting used by spammers"


class VPNNetwork(NamedTuple):
    asn: int
    category: str
    provider: str
    # MaxMind's name for the network's owner.
    organization: str
    sources: tuple[str, ...]

    @property
    def reason(self):
        """The reason for its rule, e.g. "VPN: NordVPN (PacketHub S.A.)"."""
        if self.organization.casefold() == self.provider.casefold():
            return f"{self.category}: {self.provider}"
        return f"{self.category}: {self.provider} ({self.organization})"


VPN_NETWORKS = (
    VPNNetwork(136787, VPN, "NordVPN", "PacketHub S.A.", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(272096, VPN, "NordVPN", "PACKETHUB S.A.", (OWNER_NAME,)),
    VPNNetwork(147049, VPN, "NordVPN", "PacketHub S.A.", (BAD_ASN_LIST,)),
    VPNNetwork(207137, VPN, "NordVPN", "PacketHub S.A.", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(141039, VPN, "NordVPN", "PacketHub S.A.", (BAD_ASN_LIST,)),
    VPNNetwork(209854, VPN, "Surfshark", "Cyberzone S.A.", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(208172, VPN, "Proton VPN", "Proton AG", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(62371, VPN, "Proton VPN", "Proton AG", (BAD_ASN_LIST,)),
    VPNNetwork(199218, VPN, "Proton VPN", "Proton AG", (BAD_ASN_LIST,)),
    VPNNetwork(209103, VPN, "Proton VPN", "Proton AG", (BAD_ASN_LIST,)),
    VPNNetwork(
        198605,
        VPN,
        "Avast SecureLine and HMA",
        "AVAST Software s.r.o.",
        (BAD_ASN_LIST,),
    ),
    VPNNetwork(42201, VPN, "PrivateVPN", "PVDataNet AB", (BAD_ASN_LIST,)),
    VPNNetwork(46253, VPN, "IPVanish", "IPVanish, Inc.", (BAD_ASN_LIST,)),
    VPNNetwork(45748, VPN, "Private Internet Access", "PIA", (BAD_ASN_LIST,)),
    VPNNetwork(397540, VPN, "Windscribe", "Windscribe", (BAD_ASN_LIST,)),
    VPNNetwork(216025, VPN, "Mullvad", "Mullvad VPN AB", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(203619, VPN, "IVPN", "IVPN Limited", (OWNER_NAME,)),
    VPNNetwork(208765, VPN, "Bullet Proof VPN", "Bullet Proof VPN Ltd", (OWNER_NAME,)),
    VPNNetwork(397282, VPN, "Castle VPN", "Castle VPN", (OWNER_NAME,)),
    VPNNetwork(394104, VPN, "IPLockVPN", "IPLOCKVPN.COM", (OWNER_NAME,)),
    VPNNetwork(62635, VPN, "VPNWholesaler", "VPNWholesaler.com", (OWNER_NAME,)),
    VPNNetwork(218908, VPN, "SSS VPN", "Sss Vpn Technical Co., Ltd.", (OWNER_NAME,)),
    VPNNetwork(49134, VPN, "10VPN", "10VPN Research Network LTD", (OWNER_NAME,)),
    VPNNetwork(
        60729,
        TOR,
        "Stiftung Erneuerbare Freiheit",
        "Stiftung Erneuerbare Freiheit",
        (X4BNET,),
    ),
    VPNNetwork(401401, TOR, "Unredacted Inc", "Unredacted Inc", (X4BNET,)),
    VPNNetwork(401720, TOR, "Unredacted Inc", "Unredacted Inc", (X4BNET,)),
    VPNNetwork(9009, VPN_HOSTING, "M247", "M247 Europe SRL", (X4BNET, BAD_ASN_LIST)),
    VPNNetwork(51332, VPN_HOSTING, "M247", "M247 Europe SRL", (OWNER_NAME,)),
    VPNNetwork(
        212238,
        VPN_HOSTING,
        "Datacamp (CDN77)",
        "Datacamp Limited",
        (X4BNET, BAD_ASN_LIST),
    ),
    VPNNetwork(
        60068, VPN_HOSTING, "Datacamp (CDN77)", "Datacamp Limited", (BAD_ASN_LIST,)
    ),
    VPNNetwork(
        211612, VPN_HOSTING, "Datacamp (CDN77)", "Datacamp Limited", (BAD_ASN_LIST,)
    ),
    VPNNetwork(
        14618, SPAM_HOSTING, "Amazon Web Services", "Amazon.com, Inc.", (SPAM_SIGNUPS,)
    ),
    VPNNetwork(
        16509, SPAM_HOSTING, "Amazon Web Services", "Amazon.com, Inc.", (SPAM_SIGNUPS,)
    ),
    VPNNetwork(62240, SPAM_HOSTING, "Clouvider", "Clouvider Limited", (SPAM_SIGNUPS,)),
    VPNNetwork(21859, SPAM_HOSTING, "Zenlayer", "Zenlayer Inc", (SPAM_SIGNUPS,)),
    VPNNetwork(393886, SPAM_HOSTING, "Leaseweb", "Leaseweb USA, Inc.", (SPAM_SIGNUPS,)),
    # Leaseweb's other networks, which spammers can as easily rent servers on.
    VPNNetwork(30633, SPAM_HOSTING, "Leaseweb", "Leaseweb USA, Inc.", (OWNER_NAME,)),
    VPNNetwork(
        60781, SPAM_HOSTING, "Leaseweb", "LeaseWeb Netherlands B.V.", (OWNER_NAME,)
    ),
    VPNNetwork(63023, SPAM_HOSTING, "GTHost", "GTHost", (SPAM_SIGNUPS,)),
    VPNNetwork(11878, SPAM_HOSTING, "tzulo", "tzulo, inc.", (SPAM_SIGNUPS,)),
)
