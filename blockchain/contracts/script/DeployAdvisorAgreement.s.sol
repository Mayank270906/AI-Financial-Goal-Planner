// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/AdvisorAgreement.sol";

contract DeployAdvisorAgreement is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("Deployer address:", deployer);
        console.log("Deployer balance:", deployer.balance);

        vm.startBroadcast(deployerPrivateKey);

        // deployer is both admin and goalPathAI initially
        // Update goalPathAI to the Rust API wallet after deployment
        AdvisorAgreement advisor = new AdvisorAgreement(deployer, deployer);

        vm.stopBroadcast();

        console.log("========================================");
        console.log("AdvisorAgreement deployed at:", address(advisor));
        console.log("Admin:", deployer);
        console.log("GoalPathAI operator:", deployer);
        console.log("========================================");
        console.log("Etherscan: https://sepolia.etherscan.io/address/", address(advisor));
    }
}
