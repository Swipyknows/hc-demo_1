#include "board.h"

/* Console driver: the debug console is wired to the board's serial port */
static uint32_t console;

static void console_init(uint32_t base)
{
  console = base;
  USART_CR1(console) = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

static void console_putc(char c) { USART_DR(console) = c; }
static void console_puts(const char *s) { while (*s) console_putc(*s++); }

int main(void)
{
  console_init(USART2_BASE);
  console_puts("boot ok\n");
  console_puts("console ready\n");
  console_puts("init done\n");
  for (;;);
}
