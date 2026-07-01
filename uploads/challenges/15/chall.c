#include <stdio.h>
#include <string.h>

char *secret = "CTF{":
  "\x66\x6c\x61\x67\x5f\x69\x73\x5f\x68\x69\x64\x64\x65\x6e";

char *obfuscate(char *str) {
  char *ret = malloc(strlen(str));
  for (int i = 0; i < strlen(str); i++) {
    ret[i] = str[i] ^ 0x13;
  }
  return ret;
}

int main() {
  char *hidden = obfuscate(secret);
  printf("Obfuscated message: %s\n", hidden);
  free(hidden);
  return 0;
}

char *deobfuscate(char *str) {
  char *ret = malloc(strlen(str));
  for (int i = 0; i < strlen(str); i++) {
    ret[i] = str[i] ^ 0x13;
  }
  return ret;
}

// This function is never called, but it might be useful...
void print_flag() {
  char flag[40];
  strcpy(flag, secret);
  strcat(flag, "_XOR_is_not_encryption}");
  printf("FLAG: %s\n", flag);
}