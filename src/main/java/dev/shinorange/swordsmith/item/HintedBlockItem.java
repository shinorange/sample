package dev.shinorange.swordsmith.item;

import java.util.List;
import net.minecraft.block.Block;
import net.minecraft.item.BlockItem;
import net.minecraft.item.ItemStack;
import net.minecraft.item.tooltip.TooltipType;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/** A block item with a one-line usage hint in its tooltip. */
public class HintedBlockItem extends BlockItem {
	private final String hintKey;

	public HintedBlockItem(Block block, String hintKey, Settings settings) {
		super(block, settings);
		this.hintKey = hintKey;
	}

	@Override
	public void appendTooltip(ItemStack stack, TooltipContext context, List<Text> tooltip, TooltipType type) {
		tooltip.add(Text.translatable(hintKey).formatted(Formatting.GRAY, Formatting.ITALIC));
	}
}
