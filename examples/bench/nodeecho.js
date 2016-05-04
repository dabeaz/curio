// Taken from http://learn.bevry.me/node/server/
// Simple install node.js,
// run with (e.g.):
// $ /usr/local/bin/node nodeecho.js

var net = require('net');
net.createServer(function(socket){
    socket.on('data', function(data){
        socket.write(data)
    });
}).listen(25000);
