import collections
import csv
import sys
from typing import NamedTuple

from django.conf import settings
from django.core.management.base import BaseCommand

from web import geoip
from web.models import BlockRule, Visitor, describe

# Results, as written to CSV.
ENTIRE_SITE = "entire site"
PARTICIPATION = "participation"
NOT_BLOCKED = "not blocked"
INVALID = "not an IP address"

# How many of the unblocked addresses' commonest networks and countries to show.
TOP = 10


class Command(BaseCommand):
    help = (
        "Check IP addresses, e.g. known spammers', against the block rules in "
        "effect, showing which rule blocks each one and its country and network "
        "owner. Pass the addresses as arguments, or - to read them from standard "
        "input, one per line."
    )
    # So tests can pass in standard input.
    stealth_options = ("stdin",)

    def add_arguments(self, parser):
        parser.add_argument(
            "addresses",
            nargs="+",
            metavar="address",
            help="IP addresses, or - to read them from standard input. Blank lines "
            "and anything after a # are ignored.",
        )
        parser.add_argument(
            "--csv",
            action="store_true",
            dest="as_csv",
            help="Write one CSV row per address, for a spreadsheet. The summary "
            "goes to standard error.",
        )

    def handle(self, *args, addresses, as_csv=False, **options):
        stdin = options.get("stdin", sys.stdin)
        self.warn_about_problems()
        results = [
            self.check_address(address) for address in self.read(addresses, stdin)
        ]
        if as_csv:
            self.write_csv(results)
            summary = self.stderr
        else:
            for result in results:
                self.stdout.write(result.line)
            summary = self.stdout
        self.write_summary(results, summary)

    def warn_about_problems(self):
        if not settings.BLOCK_RULES_ENABLED:
            self.stderr.write(
                self.style.WARNING(
                    "Block rules are switched off (BLOCK_RULES_ENABLED is false), "
                    "so no address is blocked."
                )
            )
        for edition in geoip.EDITIONS:
            problem = geoip.problem(edition)
            if problem:
                self.stderr.write(
                    self.style.WARNING(
                        f"Can't look up countries or network owners in {edition}, "
                        f"because {problem}, so rules that need it block no one."
                    )
                )

    def read(self, addresses, stdin):
        """The addresses to check, in order, reading standard input for -."""
        for address in addresses:
            lines = stdin if address == "-" else [address]
            for line in lines:
                line = line.split("#", 1)[0].strip()
                if line:
                    yield line

    def check_address(self, address):
        try:
            visitor = Visitor(address)
        except ValueError:
            return Result(address, INVALID, None, None, f"{address}: {INVALID}")
        block = BlockRule.site_block(address)
        if block:
            outcome = ENTIRE_SITE
            what = "blocked from the entire site"
        else:
            block = BlockRule.participation_block(address)
            outcome = PARTICIPATION if block else NOT_BLOCKED
            what = "blocked from participating"
        if block:
            what += f" by rule {block.rule.pk} ({block.rule.value})"
        else:
            what = NOT_BLOCKED
        return Result(address, outcome, block, visitor, f"{describe(visitor)}: {what}")

    def write_csv(self, results):
        writer = csv.writer(self.stdout)
        writer.writerow(
            [
                "address",
                "blocked from",
                "rule",
                "rule value",
                "country",
                "asn",
                "network owner",
            ]
        )
        for result in results:
            visitor = result.visitor
            asn = visitor and visitor.asn
            writer.writerow(
                [
                    result.address,
                    result.outcome,
                    result.block.rule.pk if result.block else "",
                    result.block.rule.value if result.block else "",
                    (visitor and visitor.country) or "",
                    f"AS{asn.number}" if asn else "",
                    asn.organization if asn else "",
                ]
            )

    def write_summary(self, results, out):
        counts = collections.Counter(result.outcome for result in results)
        out.write(
            f"\nChecked {len(results)} address(es): {counts[ENTIRE_SITE]} blocked from "
            f"the entire site, {counts[PARTICIPATION]} blocked from participating, "
            f"{counts[NOT_BLOCKED]} not blocked, and {counts[INVALID]} not IP "
            "addresses."
        )
        unblocked = [
            result.visitor for result in results if result.outcome == NOT_BLOCKED
        ]
        if not unblocked:
            return
        # To help decide whether a new network owner or country rule would
        # catch them.
        networks = collections.Counter(
            f"AS{visitor.asn.number}"
            + (f" ({visitor.asn.organization})" if visitor.asn.organization else "")
            if visitor.asn
            else "Unknown network"
            for visitor in unblocked
        )
        countries = collections.Counter(
            visitor.country or "Unknown country" for visitor in unblocked
        )
        for heading, counter in (
            ("networks", networks),
            ("countries", countries),
        ):
            out.write(f"\nThe unblocked addresses' commonest {heading}:")
            for name, count in counter.most_common(TOP):
                out.write(f"  {name}: {count}")


class Result(NamedTuple):
    address: str
    # ENTIRE_SITE, PARTICIPATION, NOT_BLOCKED or INVALID.
    outcome: str
    # The web.models.Block, if blocked.
    block: object
    # The web.models.Visitor, unless the address is invalid.
    visitor: object
    # The line to show for it.
    line: str
