package dev.shinorange.swordsmith.item;

import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.registry.ModComponents;
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
		Float quality = stack.get(ModComponents.SWORD_QUALITY);
		if (quality != null) {
			tooltip.add(Text.translatable("tooltip.swordsmith.quality",
					Math.round(quality * 100f), Quality.gradeText(quality)));
		}
		tooltip.add(Text.translatable("item.swordsmith.forged_steel_sword.hint").formatted(Formatting.GRAY, Formatting.ITALIC));
	}
}
