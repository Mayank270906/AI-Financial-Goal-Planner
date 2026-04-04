// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/FinancialPassport.sol";

contract FinancialPassportTest is Test {
    FinancialPassport public passport;
    address public goalPathAI;
    address public user1;
    address public user2;
    address public attacker;

    bytes32 constant PLAN_HASH_1 = keccak256("GoalPath Plan v1 for user1");
    bytes32 constant PLAN_HASH_2 = keccak256("GoalPath Plan v2 for user1 - updated");
    bytes32 constant WRONG_HASH  = keccak256("completely wrong hash");

    function setUp() public {
        goalPathAI = address(this); // test contract acts as GoalPath AI
        user1 = makeAddr("user1");
        user2 = makeAddr("user2");
        attacker = makeAddr("attacker");

        passport = new FinancialPassport(goalPathAI);
    }

    // ──────────────────────────────────────────────
    // Test: Mint succeeds, passport stored correctly
    // ──────────────────────────────────────────────
    function testMint() public {
        passport.mint(user1, PLAN_HASH_1);

        (bytes32 planHash, uint256 timestamp, uint16 version, bool isValid) = passport.getPassport(user1);

        assertEq(planHash, PLAN_HASH_1, "Plan hash mismatch");
        assertEq(timestamp, block.timestamp, "Timestamp mismatch");
        assertEq(version, 1, "Version should be 1");
        assertTrue(isValid, "Passport should be valid");

        // Verify token ownership
        uint256 tokenId = passport.tokenIds(user1);
        assertEq(tokenId, 1, "Token ID should be 1");
        assertEq(passport.ownerOf(tokenId), user1, "Owner mismatch");
        assertEq(passport.tokenOwners(tokenId), user1, "tokenOwners mapping mismatch");
    }

    // ──────────────────────────────────────────────
    // Test: Second mint to same wallet reverts
    // ──────────────────────────────────────────────
    function testMintTwiceFails() public {
        passport.mint(user1, PLAN_HASH_1);

        vm.expectRevert(FinancialPassport.PassportAlreadyExists.selector);
        passport.mint(user1, PLAN_HASH_2);
    }

    // ──────────────────────────────────────────────
    // Test: updateHash — version increments, new hash stored
    // ──────────────────────────────────────────────
    function testUpdateHash() public {
        passport.mint(user1, PLAN_HASH_1);

        // Warp forward to get a different timestamp
        vm.warp(block.timestamp + 1 days);

        passport.updateHash(user1, PLAN_HASH_2);

        (bytes32 planHash, uint256 timestamp, uint16 version, bool isValid) = passport.getPassport(user1);

        assertEq(planHash, PLAN_HASH_2, "Hash should be updated");
        assertEq(version, 2, "Version should be 2");
        assertTrue(isValid, "Passport should still be valid");
        assertEq(timestamp, block.timestamp, "Timestamp should be updated");
    }

    // ──────────────────────────────────────────────
    // Test: updateHash reverts if no passport exists
    // ──────────────────────────────────────────────
    function testUpdateHashUnmintedFails() public {
        vm.expectRevert(FinancialPassport.PassportDoesNotExist.selector);
        passport.updateHash(user1, PLAN_HASH_1);
    }

    // ──────────────────────────────────────────────
    // Test: verify — true for matching hash, false for wrong
    // ──────────────────────────────────────────────
    function testVerify() public {
        passport.mint(user1, PLAN_HASH_1);

        assertTrue(passport.verify(user1, PLAN_HASH_1), "Should verify correctly");
        assertFalse(passport.verify(user1, WRONG_HASH), "Should reject wrong hash");
        assertFalse(passport.verify(user2, PLAN_HASH_1), "Should reject unminted wallet");
    }

    // ──────────────────────────────────────────────
    // Test: Soulbound — transfer attempt reverts
    // ──────────────────────────────────────────────
    function testSoulbound() public {
        passport.mint(user1, PLAN_HASH_1);
        uint256 tokenId = passport.tokenIds(user1);

        // Attempt transferFrom — should revert
        vm.prank(user1);
        vm.expectRevert(FinancialPassport.SoulboundTransferNotAllowed.selector);
        passport.transferFrom(user1, user2, tokenId);

        // Attempt safeTransferFrom — should also revert
        vm.prank(user1);
        vm.expectRevert(FinancialPassport.SoulboundTransferNotAllowed.selector);
        passport.safeTransferFrom(user1, user2, tokenId);
    }

    // ──────────────────────────────────────────────
    // Test: Only GoalPathAI can mint
    // ──────────────────────────────────────────────
    function testOnlyGoalPathAICanMint() public {
        vm.prank(attacker);
        vm.expectRevert(FinancialPassport.Unauthorized.selector);
        passport.mint(user1, PLAN_HASH_1);
    }

    // ──────────────────────────────────────────────
    // Test: EIP-5192 locked() always returns true
    // ──────────────────────────────────────────────
    function testLockedReturnsTrue() public {
        passport.mint(user1, PLAN_HASH_1);
        uint256 tokenId = passport.tokenIds(user1);

        assertTrue(passport.locked(tokenId), "Token should always be locked");

        // Mint another and check
        passport.mint(user2, PLAN_HASH_2);
        uint256 tokenId2 = passport.tokenIds(user2);
        assertTrue(passport.locked(tokenId2), "Token 2 should also be locked");
    }
}
