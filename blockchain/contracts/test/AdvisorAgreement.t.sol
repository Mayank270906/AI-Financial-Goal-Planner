// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/AdvisorAgreement.sol";

contract AdvisorAgreementTest is Test {
    AdvisorAgreement public agreement;
    address public admin;
    address public goalPathAI;
    address public advisor1;
    address public advisor2;
    address public user1;
    address public attacker;

    string constant PLAN_ID = "plan_abc123";
    string constant SEBI_NUM = "INA000012345";
    bytes32 constant PLAN_HASH = keccak256("user1 financial plan data");
    bytes32 constant RECOMMENDATION_HASH = keccak256("advisor recommendation data");
    bytes32 constant APPROVAL_HASH = keccak256("user approval signature");
    bytes32 constant NEW_PLAN_HASH = keccak256("updated plan after advice");

    function setUp() public {
        admin = makeAddr("admin");
        goalPathAI = address(this); // test contract acts as GoalPath AI
        advisor1 = makeAddr("advisor1");
        advisor2 = makeAddr("advisor2");
        user1 = makeAddr("user1");
        attacker = makeAddr("attacker");

        agreement = new AdvisorAgreement(admin, goalPathAI);
    }

    // ──────────────────────────────────────────────
    // Test: Register advisor — stored, not verified
    // ──────────────────────────────────────────────
    function testRegisterAdvisor() public {
        agreement.registerAdvisor(advisor1, SEBI_NUM);

        (address wallet, string memory sebiNumber, bool isVerified, uint256 registeredAt) =
            agreement.advisors(advisor1);

        assertEq(wallet, advisor1, "Wallet mismatch");
        assertEq(sebiNumber, SEBI_NUM, "SEBI number mismatch");
        assertFalse(isVerified, "Should not be verified yet");
        assertEq(registeredAt, block.timestamp, "Registration timestamp mismatch");
    }

    // ──────────────────────────────────────────────
    // Test: Admin verifies advisor
    // ──────────────────────────────────────────────
    function testVerifyAdvisor() public {
        agreement.registerAdvisor(advisor1, SEBI_NUM);

        // Verify as admin
        vm.prank(admin);
        agreement.verifyAdvisor(advisor1);

        (, , bool isVerified, ) = agreement.advisors(advisor1);
        assertTrue(isVerified, "Should be verified after admin call");
    }

    // ──────────────────────────────────────────────
    // Test: Log all 6 event types in order
    // ──────────────────────────────────────────────
    function testLogAllSixEvents() public {
        // Event 0: AGREEMENT_CREATED
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.AGREEMENT_CREATED,
                planId: PLAN_ID,
                primaryHash: PLAN_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 1 ether,
                durationDays: 30,
                serviceScope: "Full financial planning",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );

        // Event 1: PLAN_SHARED — user's plan hash goes to advisor (on-chain as hash)
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.PLAN_SHARED,
                planId: PLAN_ID,
                primaryHash: PLAN_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 0,
                durationDays: 0,
                serviceScope: "",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );

        // Event 2: ADVISOR_RECOMMENDATION — CA's recommendation hash
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.ADVISOR_RECOMMENDATION,
                planId: PLAN_ID,
                primaryHash: RECOMMENDATION_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 0,
                durationDays: 0,
                serviceScope: "",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );

        // Event 3: USER_APPROVAL — user's cryptographic consent
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.USER_APPROVAL,
                planId: PLAN_ID,
                primaryHash: APPROVAL_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 0,
                durationDays: 0,
                serviceScope: "",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );

        // Event 4: PLAN_UPDATED_AFTER_ADVICE — old vs new hash delta
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.PLAN_UPDATED_AFTER_ADVICE,
                planId: PLAN_ID,
                primaryHash: NEW_PLAN_HASH,
                secondaryHash: PLAN_HASH, // old hash
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 0,
                durationDays: 0,
                serviceScope: "",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );

        // Event 5: ENGAGEMENT_CLOSED — outcome + fee
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.ENGAGEMENT_CLOSED,
                planId: PLAN_ID,
                primaryHash: NEW_PLAN_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 1 ether,
                durationDays: 0,
                serviceScope: "",
                outcome: "completed",
                feeReleased: true,
                timestamp: block.timestamp
            })
        );

        // Verify all 6 events are retrieval
        AdvisorAgreement.EngagementEvent[] memory events = agreement.getEvents(PLAN_ID);
        assertEq(events.length, 6, "Should have 6 events");

        // Verify event types in order
        assertEq(uint8(events[0].eventType), uint8(AdvisorAgreement.EventType.AGREEMENT_CREATED));
        assertEq(uint8(events[1].eventType), uint8(AdvisorAgreement.EventType.PLAN_SHARED));
        assertEq(uint8(events[2].eventType), uint8(AdvisorAgreement.EventType.ADVISOR_RECOMMENDATION));
        assertEq(uint8(events[3].eventType), uint8(AdvisorAgreement.EventType.USER_APPROVAL));
        assertEq(uint8(events[4].eventType), uint8(AdvisorAgreement.EventType.PLAN_UPDATED_AFTER_ADVICE));
        assertEq(uint8(events[5].eventType), uint8(AdvisorAgreement.EventType.ENGAGEMENT_CLOSED));

        // Verify PLAN_UPDATED_AFTER_ADVICE has both hashes
        assertEq(events[4].primaryHash, NEW_PLAN_HASH, "New hash mismatch");
        assertEq(events[4].secondaryHash, PLAN_HASH, "Old hash mismatch");

        // Verify ENGAGEMENT_CLOSED outcome
        assertEq(events[5].outcome, "completed");
        assertTrue(events[5].feeReleased);
    }

    // ──────────────────────────────────────────────
    // Test: getEvents returns correct count
    // ──────────────────────────────────────────────
    function testGetEventsReturnsCorrectCount() public {
        // Log 6 events
        for (uint8 i = 0; i < 6; i++) {
            agreement.logEvent(
                AdvisorAgreement.EngagementEvent({
                    eventType: AdvisorAgreement.EventType(i),
                    planId: PLAN_ID,
                    primaryHash: PLAN_HASH,
                    secondaryHash: bytes32(0),
                    userWallet: user1,
                    advisorWallet: advisor1,
                    feeAmount: 0,
                    durationDays: 0,
                    serviceScope: "",
                    outcome: "",
                    feeReleased: false,
                    timestamp: block.timestamp
                })
            );
        }

        assertEq(agreement.getEventCount(PLAN_ID), 6, "Should count 6 events");
        assertEq(agreement.getEvents(PLAN_ID).length, 6, "Should return 6 events");
    }

    // ──────────────────────────────────────────────
    // Test: Only GoalPathAI can log events
    // ──────────────────────────────────────────────
    function testOnlyGoalPathAICanLog() public {
        vm.prank(attacker);
        vm.expectRevert(AdvisorAgreement.Unauthorized.selector);
        agreement.logEvent(
            AdvisorAgreement.EngagementEvent({
                eventType: AdvisorAgreement.EventType.AGREEMENT_CREATED,
                planId: PLAN_ID,
                primaryHash: PLAN_HASH,
                secondaryHash: bytes32(0),
                userWallet: user1,
                advisorWallet: advisor1,
                feeAmount: 0,
                durationDays: 0,
                serviceScope: "",
                outcome: "",
                feeReleased: false,
                timestamp: block.timestamp
            })
        );
    }
}
