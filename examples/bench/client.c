#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <arpa/inet.h>

int main() {
  int sockfd;
  struct sockaddr_in servaddr;
  char outgoing[100];
  char incoming[100];
  int  n;

  sockfd = socket(AF_INET, SOCK_STREAM, 0);
  bzero(&servaddr, sizeof(servaddr));
  bzero(incoming, 100);
  servaddr.sin_family = AF_INET;
  servaddr.sin_port = htons(25000);
  inet_pton(AF_INET, "127.0.0.1", &servaddr.sin_addr);
  connect(sockfd, &servaddr, sizeof(servaddr));

  strcpy(outgoing, "test");
  for (n = 0; n < 1000000; n++) {
    send(sockfd, outgoing, 1, 0);
    recv(sockfd, incoming, 1, 0);
    if ((n % 10000) == 0) {
      printf("%d\n", n);
    }
  }
  close(sockfd);
}


   
