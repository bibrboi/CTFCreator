#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MAX_SIZE 100

void receive_message(char *message) {
    char buffer[MAX_SIZE];
    strcpy(buffer, message);
    printf("Received message: %s\n", buffer);
}

int main() {
    char message[1024];
    printf("Enter a message: ");
    fgets(message, 1024, stdin);
    message[strcspn(message, "\n")] = 0;
    receive_message(message);
    return 0;
}
