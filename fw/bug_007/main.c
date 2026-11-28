#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

/* Byte FIFO between the receive path and the command parser */
#define FIFO_SIZE 4
static struct {
  char data[FIFO_SIZE];
  uint32_t head;
  uint32_t tail;
} fifo;

static void fifo_push(char c)
{
  fifo.data[fifo.head] = c;
  if (++fifo.head >= FIFO_SIZE) fifo.head = 0;
}

static char fifo_pop(void)
{
  char c = fifo.data[fifo.tail];
  if (++fifo.tail > FIFO_SIZE) fifo.tail = 0;
  return c;
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");

  const char *in = "abcdef";
  char out[8];
  int n = 0;
  fifo_push(in[0]); fifo_push(in[1]); fifo_push(in[2]); fifo_push(in[3]);
  out[n++] = fifo_pop(); out[n++] = fifo_pop();
  fifo_push(in[4]); fifo_push(in[5]);
  out[n++] = fifo_pop(); out[n++] = fifo_pop(); out[n++] = fifo_pop(); out[n++] = fifo_pop();
  out[n] = 0;

  uart_puts("data: ");
  for (int i = 0; i < n; i++)
    uart_putc((out[i] >= 'a' && out[i] <= 'z') ? out[i] : '?');
  uart_puts("\n");
  uart_puts("init done\n");
  for (;;);
}
