// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title IERC5192 — Minimal Soulbound Token Interface
/// @dev See https://eips.ethereum.org/EIPS/eip-5192
interface IERC5192 {
    /// @notice Emitted when the locking status is changed to locked.
    /// @param tokenId The identifier for a token.
    event Locked(uint256 tokenId);

    /// @notice Emitted when the locking status is changed to unlocked.
    /// @param tokenId The identifier for a token.
    event Unlocked(uint256 tokenId);

    /// @notice Returns the locking status of an Soulbound Token
    /// @param tokenId The identifier for a token.
    function locked(uint256 tokenId) external view returns (bool);
}
