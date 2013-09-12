portcullis
==========

A transparent encrypting proxy for the Swift object store using the Barbarian key management system. 

Prototype Folder
=========
The 'prototype' folder contains Python modules that test out a chunked-request/response proxy based 
on Tornado. Details on caveats and functionalty are found at the top of the prototype/crypto_proxy.py
module.

These files aren't meant to be final articles, though one of them (prototype/crypto_proxy.py)
is a step towards a final approach. The module prototype/test_runner.py generates a simple chunked POST for
testing purposes. The prototype/testdata_out.txt file is a simple text file that can be sent with a curl
command (below). The remaining files are throw away eventually, but together act as a stand-in 'target' 
server as follows.

You can run a simple demo that sends the contents of 'testdata_out.txt' to the chunked proxy, which then mock encrypts
the chunk, and then sends a chunked request of this data to the target server. Follow these steps:

1. Create a virtual environment, and `pip install -r tools/pip-requires` in it.
2. Change to the 'prototype' folder.
3. Run 'python crypto_proxy.py -port=8000' from one terminal (this is the Swift Proxy prototype).
4. Run 'python main.py -port=8080' from another terminal (this mimics a Swift target).
5. Run 'curl -v -H "Transfer-Encoding: chunked" -H "Expect: 100-continue" --data-binary @testdata_out.txt http://localhost:8000/chunked'

You should see positive activity on both servers, with all-caps being received on the target side.


