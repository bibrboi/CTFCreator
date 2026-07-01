#include <stdio.h>
#include <string.h>

char flag[] = {0x74, 0x72, 0x65, 0x76, 0x6e, 0x75, 0x6f, 0x73, 0x5f, 0x61, 0x72, 0x65, 0x5f, 0x66, 0x75, 0x6e};
char reversed[20];

void reverse_string(char* str, char* output) {
    int length = strlen(str);
    for(int i = 0; i < length; i++) {
        output[i] = str[length - i - 1];
    }
    output[length] = '\0';
}

int main() {
    printf("Welcome to the messaging app!\n");
    reverse_string(flag, reversed);
    for(int i = 0; i < strlen(reversed); i++) {
        reversed[i] = reversed[i] ^ 0x55;
    }
    // printf("%s\n", reversed);
    return 0;
}