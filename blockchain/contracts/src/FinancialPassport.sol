// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "./IERC5192.sol";

/// @title FinancialPassport — Soulbound Financial Identity NFT
/// @notice A non-transferable NFT that stores a SHA-256 hash of the user's
///         GoalPath AI financial plan on-chain. Implements EIP-5192 for soulbound enforcement.
/// @dev Only the GoalPath AI operator address can mint and update passports.
contract FinancialPassport is ERC721, IERC5192 {

    struct Passport {
        bytes32 planHash;      // SHA-256 hash of the GoalPath AI plan
        uint256 timestamp;     // block.timestamp of last update
        uint16  version;       // increments on every updateHash call
        bool    isValid;       // false if passport is revoked
    }

    mapping(address => Passport)  public passports;
    mapping(address => uint256)   public tokenIds;
    mapping(uint256 => address)   public tokenOwners;

    address public goalPathAI;   // only this address can mint/update
    uint256 private _nextTokenId;

    // ──────────────────────────────────────────────
    // Events
    // ──────────────────────────────────────────────

    event PassportMinted(address indexed user, uint256 tokenId, bytes32 planHash);
    event PassportUpdated(address indexed user, bytes32 newHash, uint16 newVersion);

    // ──────────────────────────────────────────────
    // Errors
    // ──────────────────────────────────────────────

    error Unauthorized();
    error PassportAlreadyExists();
    error PassportDoesNotExist();
    error SoulboundTransferNotAllowed();

    // ──────────────────────────────────────────────
    // Modifiers
    // ──────────────────────────────────────────────

    modifier onlyGoalPathAI() {
        if (msg.sender != goalPathAI) revert Unauthorized();
        _;
    }

    // ──────────────────────────────────────────────
    // Constructor
    // ──────────────────────────────────────────────

    constructor(address _goalPathAI) ERC721("GoalPath Financial Passport", "GPASS") {
        goalPathAI = _goalPathAI;
        _nextTokenId = 1; // token IDs start at 1
    }

    // ──────────────────────────────────────────────
    // Core Functions
    // ──────────────────────────────────────────────

    /// @notice Mint a new soulbound Financial Passport for a user.
    /// @param userWallet The wallet address to mint the passport to.
    /// @param planHash   SHA-256 hash of the user's financial plan.
    function mint(address userWallet, bytes32 planHash) external onlyGoalPathAI {
        if (passports[userWallet].isValid) revert PassportAlreadyExists();

        uint256 tokenId = _nextTokenId++;

        _safeMint(userWallet, tokenId);

        passports[userWallet] = Passport({
            planHash:  planHash,
            timestamp: block.timestamp,
            version:   1,
            isValid:   true
        });

        tokenIds[userWallet] = tokenId;
        tokenOwners[tokenId] = userWallet;

        emit PassportMinted(userWallet, tokenId, planHash);
        emit Locked(tokenId); // EIP-5192 — locked immediately on mint
    }

    /// @notice Update the plan hash for an existing passport.
    /// @param userWallet The wallet whose passport to update.
    /// @param newHash    The new SHA-256 plan hash.
    function updateHash(address userWallet, bytes32 newHash) external onlyGoalPathAI {
        if (!passports[userWallet].isValid) revert PassportDoesNotExist();

        Passport storage p = passports[userWallet];
        p.planHash  = newHash;
        p.timestamp = block.timestamp;
        p.version  += 1;

        emit PassportUpdated(userWallet, newHash, p.version);
    }

    /// @notice Get full passport data for a wallet.
    /// @return planHash  The stored plan hash.
    /// @return timestamp The last-update timestamp.
    /// @return version   The current version number.
    /// @return isValid   Whether the passport is valid.
    function getPassport(address userWallet) external view returns (bytes32, uint256, uint16, bool) {
        Passport memory p = passports[userWallet];
        return (p.planHash, p.timestamp, p.version, p.isValid);
    }

    /// @notice Verify a hash against a wallet's stored plan hash.
    /// @return True if the hashes match and the passport is valid.
    function verify(address userWallet, bytes32 hashToCheck) external view returns (bool) {
        Passport memory p = passports[userWallet];
        return p.isValid && p.planHash == hashToCheck;
    }

    // ──────────────────────────────────────────────
    // EIP-5192 — Soulbound Enforcement
    // ──────────────────────────────────────────────

    /// @notice All tokens are permanently locked (soulbound).
    function locked(uint256 tokenId) external view override returns (bool) {
        // Ensure the token exists
        _requireOwned(tokenId);
        return true;
    }

    /// @dev Override OZ v5 _update to block all transfers except minting.
    function _update(address to, uint256 tokenId, address auth) internal override returns (address) {
        address from = _ownerOf(tokenId);

        // Allow minting (from == address(0)), block all other transfers
        if (from != address(0)) revert SoulboundTransferNotAllowed();

        return super._update(to, tokenId, auth);
    }

    // ──────────────────────────────────────────────
    // ERC-165 Interface Support
    // ──────────────────────────────────────────────

    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(IERC5192).interfaceId || super.supportsInterface(interfaceId);
    }
}
