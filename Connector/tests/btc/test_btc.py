#!/usr/bin/python3
from decimal import Decimal
import pytest
import json
import time
from btc.config import Config
from btc.constants import *
from btc.websockets import BlockWebSocket
from btc.utils import convertToSatoshi, sortUnspentOutputs, decodeTransactionDetails
from logger import logger
from rpcutils.rpcconnector import RPCConnector
from httputils.httpmethod import RouteTableDef
from rpcutils.error import RpcBadRequestError
from wsutils.subscribers import ListenerSubscriber
from wsutils.wsmethod import wsMethods
from wsutils.constants import *
from wsutils import websocket

networkName = "regtest"

config = Config(
    coin=COIN_SYMBOL,
    networkName=networkName
)
config.loadConfig(
    config={
        "bitcoincoreRpcEndpoint": "http://swapper:swapper@localhost:8332",
        "electrumRpcEndpoint": "http://swapper:swapper@localhost:30000",
        "bitcoincoreZmqEndpoint": "tcp://localhost:28332",
        "bitcoinAddressCallbackHost": "http://connector:80",
        "electrsEndpoint": "localhost:60001:t"
    }
)

BlockWebSocket(
    coin=COIN_SYMBOL,
    config=config
)
websocket.startWebSockets(COIN_SYMBOL, networkName)


def makeRequest(endpoint, method, params):
    return RPCConnector.request(endpoint, 1, method, params)


def makeBitcoinCoreRequest(method, params):
    return makeRequest(config.bitcoincoreRpcEndpoint, method, params)


def makeElectrumRequest(method, params):
    return makeRequest(config.electrumRpcEndpoint, method, params)


def mineBlocksToAddress(address, numBlocks=1):
    return makeBitcoinCoreRequest("generatetoaddress", [numBlocks, address])


wallet1Name = "wallet1"
try:
    makeBitcoinCoreRequest("loadwallet", [wallet1Name])
except RpcBadRequestError:
    if wallet1Name not in makeBitcoinCoreRequest("listwallets", []):
        makeBitcoinCoreRequest("createwallet", [wallet1Name])


address1 = makeBitcoinCoreRequest("getnewaddress", [])
privateKey1 = makeBitcoinCoreRequest("dumpprivkey", [address1])
address2 = makeBitcoinCoreRequest("getnewaddress", [])
minerAddress = makeBitcoinCoreRequest("getnewaddress", [])
refundAddress1 = makeBitcoinCoreRequest("getnewaddress", [])
sub = ListenerSubscriber()
newBlocksSub = ListenerSubscriber()
mineBlocksToAddress(address1, 150)
mineBlocksToAddress(address2, 150)


def sendTransaction(fromAddress, toAddress, amount):

    signedRawTransaction, ok = createSignedRawTransaction(fromAddress, toAddress, amount)

    if not ok:
        return None, False

    if makeBitcoinCoreRequest("testmempoolaccept", [[signedRawTransaction["hex"]]]):
        return makeBitcoinCoreRequest("sendrawtransaction", [signedRawTransaction["hex"]]), True


def createSignedRawTransaction(fromAddress, toAddress, amount):

    adddressUtxos = makeBitcoinCoreRequest("listunspent", [1, 9999999, [fromAddress]])

    amountCount = 0
    transactionUtxos = []
    allowed = False

    for addressUtxo in adddressUtxos:

        amountCount += addressUtxo["amount"]
        transactionUtxos.append({
            "txid": addressUtxo["txid"],
            "vout": addressUtxo["vout"],
            "amount": addressUtxo["amount"],
            "scriptPubKey": addressUtxo["scriptPubKey"]
        })

        if amountCount > amount:
            allowed = True
            break

    if not allowed:
        logger.printError(f"Transaction without {amount} fund")
        return None, False

    rawTransaction = makeBitcoinCoreRequest("createrawtransaction", [
        [{key: transactionUtxo[key] for key in ("txid", "vout") if key in transactionUtxo} for transactionUtxo in transactionUtxos],
        [{toAddress: amount}],
        0,
        True
    ])

    fundTransactionResponse = makeBitcoinCoreRequest("fundrawtransaction", [
        rawTransaction,
        {
            "changeAddress": refundAddress1,
            "includeWatching": False,
            "feeRate": 0.00005,
            "replaceable": True,
            "changePosition": 1,
            "subtractFeeFromOutputs": [0]
        }
    ])

    signedRawTransaction = makeBitcoinCoreRequest("signrawtransactionwithwallet", [
        fundTransactionResponse["hex"],
        [{key: transactionUtxo[key] for key in ("txid", "vout", "amount", "scriptPubKey") if key in transactionUtxo} for transactionUtxo in transactionUtxos]
    ])

    if signedRawTransaction["complete"]:
        return signedRawTransaction, True

    return None, False


def simulateTransactions(numTransations=100, amount=0.01, transactionsPerBlock=5, minerAddress=minerAddress):

    for i in range(numTransations):

        transaction, ok = sendTransaction(address1, address2, amount)

        if not ok:
            break

        logger.printInfo(f"Transaction {i} done: {transaction}")

        if i % transactionsPerBlock == 0:
            makeBitcoinCoreRequest("generatetoaddress", [1, minerAddress])
            logger.printInfo("New block generated")

    makeBitcoinCoreRequest("generatetoaddress", [1, minerAddress])
    logger.printInfo("New block generated")


def testGetBlock():

    if "getBlockByNumber" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getBlockByNumber not loaded in RPCMethods")
        assert False

    if "getBlockByHash" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getBlockByHash not loaded in RPCMethods")
        assert False

    blockNumber = 1

    expectedHash = makeBitcoinCoreRequest(GET_BLOCK_HASH_METHOD, [blockNumber])
    expectedBlock = makeBitcoinCoreRequest(GET_BLOCK_METHOD, [expectedHash, 2])

    gotByHash = RouteTableDef.httpMethods[COIN_SYMBOL]["getBlockByHash"]({"blockHash": expectedHash}, config)

    if not json.dumps(expectedBlock, sort_keys=True) == json.dumps(gotByHash, sort_keys=True):
        logger.printError(f"Get block by hash error. Expected  {expectedBlock} but Got{gotByHash}")
        assert False

    gotByNumber = RouteTableDef.httpMethods[COIN_SYMBOL]["getBlockByNumber"].handler({"blockNumber": blockNumber}, config)

    if not json.dumps(expectedBlock, sort_keys=True) == json.dumps(gotByNumber, sort_keys=True):
        logger.printError(f"Get block by number error. Expected  {expectedBlock} but Got{gotByNumber}")
        assert False

    assert True


def testGetHeight():

    if "getHeight" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getHeight not loaded in RPCMethods")
        assert False

    expectedHeight = makeBitcoinCoreRequest(GET_BLOCK_COUNT_METHOD, [])
    expectedHash = makeBitcoinCoreRequest(GET_BLOCK_HASH_METHOD, [expectedHeight])

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getHeight"].handler({}, config)

    assert got["latestBlockIndex"] == str(expectedHeight) and got["latestBlockHash"] == expectedHash


def testGetFeePerByte():

    if "getFeePerByte" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getFeePerByte not loaded in RPCMethods")
        assert False

    simulateTransactions(numTransations=50)

    confirmations = 2
    expected = makeBitcoinCoreRequest(ESTIMATE_SMART_FEE_METHOD, [confirmations])
    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getFeePerByte"].handler({"confirmations": confirmations}, config)

    assert str(expected["feerate"]) == str(float((Decimal(got["feePerByte"]) / 100000000 * 1000)))


def testBroadcastTransaction():

    if "broadcastTransaction" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("broadcastTransaction not loaded in RPCMethods")
        assert False

    signedRawTransaction, ok = createSignedRawTransaction(address1, address2, 0.5)

    if not ok:
        logger.printError("Can not create transaction to broadcasts")
        assert False

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["broadcastTransaction"].handler(
        {
            "rawTransaction": signedRawTransaction["hex"]
        },
        config
    )

    blockMinedHash = mineBlocksToAddress(minerAddress, 1)[0]
    blockMined = makeBitcoinCoreRequest(GET_BLOCK_METHOD, [blockMinedHash, 2])

    found = signedRawTransaction["hex"] in [tx["hex"] for tx in blockMined["tx"]]

    logger.printWarning(f"Transaction ID from connector is: {got['broadcasted']}")

    if not found:
        logger.printError(f"Signed raw transaction {signedRawTransaction['hex']} not found in last generated block {blockMinedHash}")
        logger.printError(f"Transaction ID from connector is: {got['broadcasted']}")
    assert found


def testGetAddressHistory():

    if "getAddressHistory" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressHistory not loaded in RPCMethods")
        assert False

    time.sleep(10)

    expected = makeElectrumRequest(GET_ADDRESS_HISTORY_METHOD, [address1])

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressHistory"].handler({"address": address1}, config)

    expectedTxHashes = {item["tx_hash"]: False for item in expected}

    for gotTxHash in got["txHashes"]:
        if gotTxHash in expectedTxHashes:
            expectedTxHashes[gotTxHash] = True
        else:
            logger.printError(f"Transaction {gotTxHash} not in expected txHashes {expectedTxHashes}")
            assert False

    for expectedTxHash in expectedTxHashes:
        if not expectedTxHashes[expectedTxHash]:
            logger.printError(f"Transaction {expectedTxHash} not in got txHashes {got['txHashes']}")
            assert False

    assert True


def testGetAddressesHistory():

    if "getAddressesHistory" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressesHistory not loaded in RPCMethods")
        assert False

    addresses = [address1, address2]

    time.sleep(10)

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressesHistory"].handler({"addresses": addresses}, config)

    for addressHistory in got:
        expected = makeElectrumRequest(GET_ADDRESS_HISTORY_METHOD, [addressHistory["address"]])
        expectedTxHashes = {item["tx_hash"]: False for item in expected}

        for gotTxHash in addressHistory["txHashes"]:
            if gotTxHash in expectedTxHashes:
                expectedTxHashes[gotTxHash] = True
            else:
                logger.printError(f"Transaction {gotTxHash} not in expected txHashes {expectedTxHashes}")
                assert False

        for expectedTxHash in expectedTxHashes:
            if not expectedTxHashes[expectedTxHash]:
                logger.printError(f"Transaction {expectedTxHash} not in got txHashes {addressHistory['txHashes']}")
                assert False

    assert True


def testGetAddressBalance():

    if "getAddressBalance" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressBalance not loaded in RPCMethods")
        assert False

    expected = makeElectrumRequest("getaddressbalance", [address1])
    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressBalance"].handler({"address": address1}, config)

    assert convertToSatoshi(expected["confirmed"]) == got["balance"]["confirmed"] and convertToSatoshi(expected["unconfirmed"]) == got["balance"]["unconfirmed"] and address1 == got["address"]


def testGetAddressesBalance():

    if "getAddressesBalance" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressesBalance not loaded in RPCMethods")
        assert False

    addresses = [address1, address2]

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressesBalance"].handler({"addresses": addresses}, config)

    for addressBalance in got:

        expected = makeElectrumRequest("getaddressbalance", [addressBalance["address"]])

        if convertToSatoshi(expected["confirmed"]) != addressBalance["balance"]["confirmed"] or convertToSatoshi(expected["unconfirmed"]) != addressBalance["balance"]["unconfirmed"]:
            logger.printError(f"Error getting balance for {addressBalance['address']}. Expected: {expected}. Got: {addressBalance['balance']}")
            assert False

    assert True


def testGetTransactionHex():

    if "getTransactionHex" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getTransactionHex not loaded in RPCMethods")
        assert False

    addressHistory = makeElectrumRequest(GET_ADDRESS_HISTORY_METHOD, [address1])
    txHash = addressHistory[0]["tx_hash"]

    expected = makeBitcoinCoreRequest(GET_RAW_TRANSACTION_METHOD, [txHash])

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getTransactionHex"].handler({"txHash": txHash}, config)

    assert expected == got["rawTransaction"]


def testGetAddressesTransactionCount():

    if "getAddressesTransactionCount" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressesTransactionCount not loaded in RPCMethods")
        assert False

    addresses = {
        "addresses": [
            {
                "address": address1,
                "pending": True
            },
            {
                "address": address2,
                "pending": False
            }
        ]
    }

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressesTransactionCount"].handler(addresses, config)

    for index, address in enumerate(addresses["addresses"]):

        expected = makeElectrumRequest(GET_ADDRESS_HISTORY_METHOD, [address["address"]])

        pendingCount = 0
        for tx in expected:
            if tx["height"] == 0:
                pendingCount += 1

        assert json.dumps(got[index], sort_keys=True) == json.dumps(
            {
                "address": address["address"],
                "transactionCount": str(pendingCount) if address["pending"] else str(len(expected) - pendingCount)
            }
        )


def testGetAddressTransactionCount():

    if "getAddressTransactionCount" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressTransactionCount not loaded in RPCMethods")
        assert False

    pending = True

    expected = makeElectrumRequest(GET_ADDRESS_HISTORY_METHOD, [address1])
    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressTransactionCount"].handler(
        {
            "address": address1,
            "pending": pending
        },
        config
    )

    pendingCount = 0
    for tx in expected:
        if tx["height"] == 0:
            pendingCount += 1

    assert json.dumps(got, sort_keys=True) == json.dumps(
        {
            "address": address1,
            "transactionCount": str(pendingCount) if pending else str(len(expected) - pendingCount)
        }
    )


def testGetAddressUnspent():

    if "getAddressUnspent" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressUnspent not loaded in RPCMethods")
        assert False

    expected = makeElectrumRequest(GET_ADDRESS_UNSPENT_METHOD, [address1])

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressUnspent"].handler({"address": address1}, config)

    got.sort(key=sortUnspentOutputs, reverse=False)

    txs = []

    for tx in expected:
        txs.append(
            {
                "txHash": tx["tx_hash"],
                "vout": str(tx["tx_pos"]),
                "status": {
                    "confirmed": tx["height"] != 0,
                    "blockHeight": str(tx["height"])
                },
                "value": str(tx["value"])
            }
        )

    txs.sort(key=sortUnspentOutputs, reverse=False)

    assert json.dumps(got, sort_keys=True) == json.dumps(txs, sort_keys=True)


def testGetAddressesUnspent():

    if "getAddressesUnspent" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getAddressesUnspent not loaded in RPCMethods")
        assert False

    addresses = [address1, address2]

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getAddressesUnspent"].handler({"addresses": addresses}, config)

    for addressUnspent in got:
        addressUnspent["outputs"].sort(key=sortUnspentOutputs, reverse=False)
        expected = makeElectrumRequest(GET_ADDRESS_UNSPENT_METHOD, [addressUnspent["address"]])

        txs = []

        for tx in expected:
            txs.append(
                {
                    "txHash": tx["tx_hash"],
                    "vout": str(tx["tx_pos"]),
                    "status": {
                        "confirmed": tx["height"] != 0,
                        "blockHeight": str(tx["height"])
                    },
                    "value": str(tx["value"])
                }
            )
        txs.sort(key=sortUnspentOutputs, reverse=False)
        if not (json.dumps(addressUnspent["outputs"], sort_keys=True) == json.dumps(txs, sort_keys=True)):
            logger.printError(f"Error getting unspent transaction for {addressUnspent['address']}. "
                              f"Expected: {txs}. Got: {addressUnspent['outputs']}")
            assert False

    assert True


def testGetTransaction():

    if "getTransaction" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getTransaction not loaded in RPCMethods")
        assert False

    txHash, _ = sendTransaction(address1, address2, 0.00001)
    mineBlocksToAddress(minerAddress, 1)

    expectedTransaction = makeBitcoinCoreRequest(GET_RAW_TRANSACTION_METHOD, [txHash, True])
    expectedBlock = makeBitcoinCoreRequest(GET_BLOCK, [expectedTransaction["blockhash"], 1])

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getTransaction"].handler({"txHash": txHash}, config)

    txDetails = decodeTransactionDetails(expectedTransaction, 0, config)

    for input in txDetails["inputs"]:
        input["amount"] = str(input["amount"])
    for output in txDetails["outputs"]:
        output["amount"] = str(output["amount"])

    assert json.dumps(
        {
            "transaction": {
                "txId": expectedTransaction["txid"],
                "txHash": expectedTransaction["hash"],
                "blockNumber": str(expectedBlock["height"]),
                "fee": str(txDetails["fee"]),
                "inputs": txDetails["inputs"],
                "outputs": txDetails["outputs"],
                "data": expectedTransaction
            }
        }, sort_keys=True) == json.dumps(got, sort_keys=True)


def testGetTransactions():

    if "getTransactions" not in RouteTableDef.httpMethods[COIN_SYMBOL]:
        logger.printError("getTransactions not loaded in RPCMethods")
        assert False

    txHashes = []
    for i in range(0, 2):

        txHash, _ = sendTransaction(address1, address2, 0.00001)
        txHashes.append(txHash)

    mineBlocksToAddress(minerAddress, 1)

    got = RouteTableDef.httpMethods[COIN_SYMBOL]["getTransactions"].handler({"txHashes": txHashes}, config)

    for txHash in txHashes:

        found = True
        for gotTransaction in got["transactions"]:
            if gotTransaction["transaction"]["txHash"] == txHash:
                found = True
                expectedTransaction = makeBitcoinCoreRequest(GET_RAW_TRANSACTION_METHOD, [txHash, True])
                expectedBlock = makeBitcoinCoreRequest(GET_BLOCK, [expectedTransaction["blockhash"], 1])
                txDetails = decodeTransactionDetails(expectedTransaction, 0, config)

                for input in txDetails["inputs"]:
                    input["amount"] = str(input["amount"])
                for output in txDetails["outputs"]:
                    output["amount"] = str(output["amount"])

                assert json.dumps(
                    {
                        "transaction": {
                            "txId": expectedTransaction["txid"],
                            "txHash": expectedTransaction["hash"],
                            "blockNumber": str(expectedBlock["height"]),
                            "fee": str(txDetails["fee"]),
                            "inputs": txDetails["inputs"],
                            "outputs": txDetails["outputs"],
                            "data": expectedTransaction
                        }
                    }, sort_keys=True) == json.dumps(gotTransaction, sort_keys=True)
        if not found:
            logger.printError(f"Can not find transaction for {txHash}")
            assert False


def testSubscribeToAddressBalance():

    if "subscribeToAddressBalance" not in wsMethods[COIN_SYMBOL]:
        logger.printError("Method subscribeToAddressBalance not loaded")
        assert False

    got = wsMethods[COIN_SYMBOL]["subscribeToAddressBalance"](
        sub,
        {
            "id": 0,
            "params": {
                "address": address1
            }
        },
        config
    )

    if not got[SUBSCRIBED]:
        logger.printError(f"Error in subscribe to address balance. Expected: True Got: {got[SUBSCRIBED]}")
        assert False

    got = wsMethods[COIN_SYMBOL]["subscribeToAddressBalance"](
        sub,
        {
            "id": 0,
            "params": {
                "address": address1
            }
        },
        config
    )

    if got[SUBSCRIBED]:
        logger.printError(f"Error in subscribe to address balance. Expected: False Got: {got[SUBSCRIBED]}")
        assert False

    assert True


def testUnsubscribeFromAddressBalance():

    if "unsubscribeFromAddressBalance" not in wsMethods[COIN_SYMBOL]:
        logger.printError("Method unsubscribeFromAddressBalance not loaded")
        assert False

    got = wsMethods[COIN_SYMBOL]["unsubscribeFromAddressBalance"](
        sub,
        {
            "id": 0,
            "params": {
                "address": address1
            }
        },
        config
    )

    if not got["unsubscribed"]:
        logger.printError(f"Error in unsubscribe from address balance. Expected: True Got: {got['unsubscribed']}")
        assert False

    got = wsMethods[COIN_SYMBOL]["unsubscribeFromAddressBalance"](
        sub,
        {
            "id": 0,
            "params": {
                "address": address1
            }
        },
        config
    )

    if got["unsubscribed"]:
        logger.printError(f"Error in unsubscribe from address balance. Expected: False Got: {got['unsubscribed']}")
        assert False

    assert True


def testSubscribeToNewBlocks():

    if "subscribeToNewBlocks" not in wsMethods[COIN_SYMBOL]:
        logger.printError("Method subscribeToNewBlocks not loaded")
        assert False

    got = wsMethods[COIN_SYMBOL]["subscribeToNewBlocks"](
        newBlocksSub,
        {
            "id": 0,
            "params": {}
        },
        config
    )

    if not got[SUBSCRIBED]:
        logger.printError(f"Error in subscribe to new blocks. Expected: True Got: {got[SUBSCRIBED]}")
        assert False

    got = wsMethods[COIN_SYMBOL]["subscribeToNewBlocks"](
        newBlocksSub,
        {
            "id": 0,
            "params": {}
        },
        config
    )

    if got[SUBSCRIBED]:
        logger.printError(f"Error in subscribe to new blocks. Expected: False Got: {got[SUBSCRIBED]}")
        assert False

    assert True


def testNewBlocksWS():

    attemps = 3
    numAttemps = 0
    mineBlocksToAddress(address1, 1)

    while not newBlocksSub.messageReceived and numAttemps < attemps:
        numAttemps += 1
        logger.printWarning(f"Subscriber {newBlocksSub.subscriberID} did not receive message at {numAttemps} attemp")
        time.sleep(1)

    assert newBlocksSub.messageReceived


def testUnsubscribeFromNewBlocks():

    if "unsubscribeFromNewBlocks" not in wsMethods[COIN_SYMBOL]:
        logger.printError("Method unsubscribeFromNewBlocks not loaded")
        assert False

    got = wsMethods[COIN_SYMBOL]["unsubscribeFromNewBlocks"](
        newBlocksSub,
        {

            "id": 0,
            "params": {}
        },
        config
    )

    if not got[UNSUBSCRIBED]:
        logger.printError(f"Error in unsubscribe from new blocks. Expected: True Got: {got[UNSUBSCRIBED]}")
        assert False

    got = wsMethods[COIN_SYMBOL]["unsubscribeFromNewBlocks"](
        newBlocksSub,
        {

            "id": 0,
            "params": {}
        },
        config
    )

    if got[UNSUBSCRIBED]:
        logger.printError(f"Error in unsubscribe from new blocks. Expected: False Got: {got[UNSUBSCRIBED]}")
        assert False

    assert True
