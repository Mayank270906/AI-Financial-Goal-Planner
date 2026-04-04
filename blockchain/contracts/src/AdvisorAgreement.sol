// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AdvisorAgreement — CA Portal 6-Event Engagement Ledger
/// @notice Records the immutable 6-event engagement lifecycle between a
///         GoalPath AI user and a registered financial advisor (CA), all on-chain.
///         All sensitive data is stored as SHA-256 hashes for privacy.
/// @dev Only GoalPath AI operator can log events. Admin can verify advisors.
contract AdvisorAgreement {

    // ──────────────────────────────────────────────
    // Enums & Structs
    // ──────────────────────────────────────────────

    enum EventType {
        AGREEMENT_CREATED,         // 0 — both parties committed
        PLAN_SHARED,               // 1 — baseline plan hash recorded (user info → CA)
        ADVISOR_RECOMMENDATION,    // 2 — recommendation hash stored (CA → user)
        USER_APPROVAL,             // 3 — user's cryptographic consent (user accepts/rejects)
        PLAN_UPDATED_AFTER_ADVICE, // 4 — old hash vs new hash delta
        ENGAGEMENT_CLOSED          // 5 — outcome + fee release
    }

    struct Advisor {
        address wallet;
        string  sebiNumber;      // SEBI registration number
        bool    isVerified;      // admin-approved
        uint256 registeredAt;
    }

    struct EngagementEvent {
        EventType  eventType;
        string     planId;
        bytes32    primaryHash;   // planHash, recommendationHash, or newHash depending on event
        bytes32    secondaryHash; // oldHash for PLAN_UPDATED_AFTER_ADVICE, otherwise 0
        address    userWallet;
        address    advisorWallet;
        uint256    feeAmount;     // only populated for AGREEMENT_CREATED
        uint8      durationDays;  // only populated for AGREEMENT_CREATED
        string     serviceScope;  // only populated for AGREEMENT_CREATED
        string     outcome;       // "completed"|"disputed"|"abandoned" — only for ENGAGEMENT_CLOSED
        bool       feeReleased;   // only for ENGAGEMENT_CLOSED
        uint256    timestamp;
    }

    // ──────────────────────────────────────────────
    // State Variables
    // ──────────────────────────────────────────────

    mapping(address => Advisor) public advisors;
    address[] public advisorList;

    mapping(string => EngagementEvent[]) internal planEvents; // planId => events[]

    address public admin;        // can verify advisors
    address public goalPathAI;   // can log events and register advisors

    // ──────────────────────────────────────────────
    // Events (Solidity events, not engagement events)
    // ──────────────────────────────────────────────

    event AdvisorRegistered(address indexed wallet, string sebiNumber);
    event AdvisorVerified(address indexed wallet);
    event EventLogged(string planId, EventType eventType, address indexed user, address indexed advisor);

    // ──────────────────────────────────────────────
    // Errors
    // ──────────────────────────────────────────────

    error Unauthorized();
    error AdvisorAlreadyRegistered();
    error AdvisorNotFound();

    // ──────────────────────────────────────────────
    // Modifiers
    // ──────────────────────────────────────────────

    modifier onlyAdmin() {
        if (msg.sender != admin) revert Unauthorized();
        _;
    }

    modifier onlyGoalPathAI() {
        if (msg.sender != goalPathAI) revert Unauthorized();
        _;
    }

    // ──────────────────────────────────────────────
    // Constructor
    // ──────────────────────────────────────────────

    constructor(address _admin, address _goalPathAI) {
        admin = _admin;
        goalPathAI = _goalPathAI;
    }

    // ──────────────────────────────────────────────
    // Advisor Registration
    // ──────────────────────────────────────────────

    /// @notice Register a new financial advisor. Called by GoalPath AI.
    /// @param wallet     The advisor's wallet address.
    /// @param sebiNumber The advisor's SEBI registration number.
    function registerAdvisor(address wallet, string calldata sebiNumber) external onlyGoalPathAI {
        if (advisors[wallet].registeredAt != 0) revert AdvisorAlreadyRegistered();

        advisors[wallet] = Advisor({
            wallet: wallet,
            sebiNumber: sebiNumber,
            isVerified: false,
            registeredAt: block.timestamp
        });

        advisorList.push(wallet);

        emit AdvisorRegistered(wallet, sebiNumber);
    }

    /// @notice Admin verifies a registered advisor.
    /// @param wallet The advisor's wallet to verify.
    function verifyAdvisor(address wallet) external onlyAdmin {
        if (advisors[wallet].registeredAt == 0) revert AdvisorNotFound();

        advisors[wallet].isVerified = true;

        emit AdvisorVerified(wallet);
    }

    /// @notice Get all registered advisors.
    /// @return Array of Advisor structs.
    function getAdvisors() external view returns (Advisor[] memory) {
        uint256 len = advisorList.length;
        Advisor[] memory result = new Advisor[](len);
        for (uint256 i = 0; i < len; i++) {
            result[i] = advisors[advisorList[i]];
        }
        return result;
    }

    // ──────────────────────────────────────────────
    // 6-Event Engagement Lifecycle
    // ──────────────────────────────────────────────

    /// @notice Log an engagement event for a plan. All data is hashed for privacy.
    /// @dev The entire CA engagement flow — from agreement creation to closure —
    ///      is recorded immutably on-chain. Sensitive user data is never stored
    ///      in plaintext; only SHA-256 hashes are recorded.
    /// @param evt The engagement event struct.
    function logEvent(EngagementEvent calldata evt) external onlyGoalPathAI {
        planEvents[evt.planId].push(evt);

        emit EventLogged(evt.planId, evt.eventType, evt.userWallet, evt.advisorWallet);
    }

    /// @notice Get all engagement events for a plan ID.
    /// @param planId The plan identifier.
    /// @return Array of EngagementEvent structs.
    function getEvents(string calldata planId) external view returns (EngagementEvent[] memory) {
        return planEvents[planId];
    }

    /// @notice Get the count of events for a plan ID.
    /// @param planId The plan identifier.
    /// @return The number of events.
    function getEventCount(string calldata planId) external view returns (uint256) {
        return planEvents[planId].length;
    }
}
