
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define BUFFER_SIZE 1024

void note_taker() {
    char buffer[BUFFER_SIZE];
    printf("Enter your note: ");
    gets(buffer);
    printf("You entered: %s\n", buffer);
}

int main() {
    note_taker();
    return 0;
}
