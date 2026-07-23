package dev.shinorange.swordsmith.item;

import java.util.List;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.item.tooltip.TooltipType;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/** A plain item with a one-line "what do I do with this" tooltip. */
public class HintedItem extends Item {
	private final String hintKey;

	public HintedItem(String hintKey, Settings settings) {
		super(settings);
		this.hintKey = hintKey;
	}

	@Override
	public void appendTooltip(ItemStack stack, TooltipContext context, List<Text> tooltip, TooltipType type) {
		tooltip.add(Text.translatable(hintKey).formatted(Formatting.GRAY, Formatting.ITALIC));
	}
}
