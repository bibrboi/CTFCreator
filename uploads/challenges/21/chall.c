
#include <stdio.h>
#include <string.h>

void print_flag() {
    char str[20];
    char key[] = "a2z";

    // Obfuscate the flag
    char obf_flag[] = "yrtraeS_gniksaer";
    for (int i = 0; i < strlen(obf_flag); i++) {
        str[i] = obf_flag[i];
    }
    str[strlen(obf_flag)] = '\0';

    // Reverse the string
    int length = strlen(str);
    char reversed[length + 1];
    for (int i = 0; i < length; i++) {
        reversed[i] = str[length - i - 1];
    }
    reversed[length] = '\0';

    // Apply XOR with the key
    for (int i = 0; i < strlen(reversed); i++) {
        reversed[i] = reversed[i] ^ key[i % strlen(key)];
    }

    printf("%s\n", reversed);
}

int main() {
    print_flag();
    return 0;
}
