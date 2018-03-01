The following command is used to create the private key and certificate.

openssl req -x509 -newkey rsa:4096 -keyout ssl_test_rsa -out ssl_test.crt -days 3650 -nodes

