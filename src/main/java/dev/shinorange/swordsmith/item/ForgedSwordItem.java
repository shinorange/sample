package dev.shinorange.swordsmith.item;

import java.util.List;
import net.minecraft.item.ItemStack;
import net.minecraft.item.SwordItem;
import net.minecraft.item.tooltip.TooltipType;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/** The finished product: a sword that exists because you forged it, not because you crafted it. */
public class ForgedSwordItem extends SwordItem {
	public ForgedSwordItem(Settings settings) {
		super(SteelToolMaterial.INSTANCE, settings);
	}

	@Override
	public void appendTooltip(ItemStack stack, TooltipContext context, List<Text> tooltip, TooltipType type) {
		super.appendTooltip(stack, context, tooltip, type);
		tooltip.add(Text.translatable("item.swordsmith.forged_steel_sword.hint").formatted(Formatting.GRAY, Formatting.ITALIC));
	}
}
