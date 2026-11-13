fw.elf: main.c link.ld
	arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -g -O0 -nostdlib -T link.ld main.c -o fw.elf
clean:
	rm -f fw.elf
