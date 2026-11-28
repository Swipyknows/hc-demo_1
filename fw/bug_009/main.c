#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

static uint32_t batches;

/* The DMA engine moves packets two at a time */
static void transfer_pair(void) { batches++; }

static void flush_queue(uint32_t pending)
{
  while (pending != 0) {
    transfer_pair();
    pending -= 2;
  }
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  flush_queue(5);
  uart_puts("batches ");
  uart_putc('0' + batches);
  uart_puts("\n");
  uart_puts("init done\n");
  for (;;);
}
