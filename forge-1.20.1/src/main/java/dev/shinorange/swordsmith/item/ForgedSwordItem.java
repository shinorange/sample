package dev.shinorange.swordsmith.item;

import dev.shinorange.swordsmith.core.Quality;
import java.util.List;
import javax.annotation.Nullable;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.SwordItem;
import net.minecraft.world.item.Tier;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;

/** The finished product: a sword that exists because you forged it, not because you crafted it. */
public class ForgedSwordItem extends SwordItem {
	public ForgedSwordItem(Tier tier, Properties properties) {
		super(tier, 3, -2.2f, properties);
	}

	@Override
	public void appendHoverText(ItemStack stack, @Nullable Level level, List<Component> tooltip, TooltipFlag flag) {
		super.appendHoverText(stack, level, tooltip, flag);
		if (stack.getTag() != null && stack.getTag().contains(Quality.SWORD_QUALITY_KEY)) {
			float quality = stack.getTag().getFloat(Quality.SWORD_QUALITY_KEY);
			tooltip.add(Component.translatable("tooltip.swordsmith.quality",
					Math.round(quality * 100f), Quality.gradeText(quality)));
		}
		tooltip.add(Component.translatable("item.swordsmith.forged_steel_sword.hint")
				.withStyle(ChatFormatting.GRAY, ChatFormatting.ITALIC));
	}
}
