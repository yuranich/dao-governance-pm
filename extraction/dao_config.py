"""
DAO configuration for event extraction.
Contains contract addresses, chains, and Snapshot space IDs.
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class DAOConfig:
    """Configuration for a single DAO."""
    name: str
    slug: str                    # table name prefix (lowercase, underscores)
    chain: str                   # ethereum | optimism | arbitrum
    governor_address: Optional[str] = None
    governor_addresses: Optional[List[str]] = None  # multiple contracts (V2+V3, governance+voting)
    snapshot_space: Optional[str] = None   # e.g., 'aave.eth'

    def get_all_addresses(self) -> List[str]:
        """Return all governor addresses (single + list)."""
        addrs = []
        if self.governor_address:
            addrs.append(self.governor_address)
        if self.governor_addresses:
            for a in self.governor_addresses:
                if a not in addrs:
                    addrs.append(a)
        return addrs


# DAO configurations for target DAOs
# Governor addresses reused from existing config.py
DAOS = [
    DAOConfig(
        name='Aave',
        slug='aave',
        chain='ethereum',
        governor_address='0xEC568fffba86c094cf06b22134B23074DFE2252c',
        governor_addresses=[
            '0xEC568fffba86c094cf06b22134B23074DFE2252c',  # Governance V2 (proposals 0-400, until Dec 2023)
            '0x9AEE0B04504CeF83A65AC3f0e838D0593BCb2BC7',  # Governance V3 (2024+, votes via L2/Snapshot)
        ],
        snapshot_space='aavedao.eth',
    ),
    DAOConfig(
        name='Arbitrum',
        slug='arbitrum',
        chain='arbitrum',
        governor_address='0x789fC99093B09aD01C34DC7251D0C89ce743e5a4',
        snapshot_space='arbitrumfoundation.eth',
    ),
    DAOConfig(
        name='Optimism',
        slug='optimism',
        chain='optimism',
        governor_address='0xcDF27F107725988f2261Ce2256bDfCdE8B382B10',
        snapshot_space='opcollective.eth',
    ),
    DAOConfig(
        name='MakerDAO',
        slug='makerdao',
        chain='ethereum',
        governor_address='0x9eF05f7F6deB616fd37aC3c959a2dDD25A108dAb',
        snapshot_space=None,  # MakerDAO uses own polling system
    ),
    DAOConfig(
        name='Compound',
        slug='compound',
        chain='ethereum',
        governor_address='0xc0Da01a04C3f3E0be433606045bB7017A7323E38',
        snapshot_space='comp-vote.eth',
    ),
    DAOConfig(
        name='Uniswap',
        slug='uniswap',
        chain='ethereum',
        governor_address='0x408ED6354d4973f66138C91495F2f2FCbd8724C3',
        snapshot_space='uniswapgovernance.eth',
    ),
    DAOConfig(
        name='Gitcoin',
        slug='gitcoin',
        chain='ethereum',
        governor_address='0x9D4C63565D5618310271bF3F3c01b2571724C1F9',
        snapshot_space='gitcoindao.eth',
    ),
    DAOConfig(
        name='ENS',
        slug='ens',
        chain='ethereum',
        governor_address='0x323A76393544d5ecca80cd6ef2A560C6a395b7E3',
        snapshot_space='ens.eth',
    ),
    DAOConfig(
        name='Lido',
        slug='lido',
        chain='ethereum',
        governor_address='0x2e59A20f205bB85a89C53f1936452ACd9879CC27',
        snapshot_space='lido-snapshot.eth',
    ),
]


def get_dao_config(dao_name: str) -> Optional[DAOConfig]:
    """Get configuration for a specific DAO by name."""
    for dao in DAOS:
        if dao.name.lower() == dao_name.lower():
            return dao
    return None


def get_all_dao_names() -> List[str]:
    """Get list of all configured DAO names."""
    return [dao.name for dao in DAOS]


def get_dao_by_slug(slug: str) -> Optional[DAOConfig]:
    """Get configuration for a specific DAO by slug."""
    for dao in DAOS:
        if dao.slug.lower() == slug.lower():
            return dao
    return None

