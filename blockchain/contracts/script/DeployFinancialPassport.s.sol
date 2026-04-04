// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/FinancialPassport.sol";

contract DeployFinancialPassport is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("Deployer address:", deployer);
        console.log("Deployer balance:", deployer.balance);

        vm.startBroadcast(deployerPrivateKey);

        FinancialPassport passport = new FinancialPassport(deployer);

        vm.stopBroadcast();

        console.log("========================================");
        console.log("FinancialPassport deployed at:", address(passport));
        console.log("GoalPathAI operator:", deployer);
        console.log("========================================");
        console.log("Etherscan: https://sepolia.etherscan.io/address/", address(passport));
    }
}
