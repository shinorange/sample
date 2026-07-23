package dev.shinorange.swordsmith.item;

import java.util.List;
import javax.annotation.Nullable;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;

/** A plain item with a one-line "what do I do with this" tooltip. */
public class HintedItem extends Item {
	private final String hintKey;

	public HintedItem(String hintKey, Properties properties) {
		super(properties);
		this.hintKey = hintKey;
	}

	@Override
	public void appendHoverText(ItemStack stack, @Nullable Level level, List<Component> tooltip, TooltipFlag flag) {
		tooltip.add(Component.translatable(hintKey).withStyle(ChatFormatting.GRAY, ChatFormatting.ITALIC));
	}
}
