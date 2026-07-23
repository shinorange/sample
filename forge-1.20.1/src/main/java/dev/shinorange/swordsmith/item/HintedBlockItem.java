package dev.shinorange.swordsmith.item;

import java.util.List;
import javax.annotation.Nullable;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;

/** A block item with a one-line usage hint in its tooltip. */
public class HintedBlockItem extends BlockItem {
	private final String hintKey;

	public HintedBlockItem(Block block, String hintKey, Properties properties) {
		super(block, properties);
		this.hintKey = hintKey;
	}

	@Override
	public void appendHoverText(ItemStack stack, @Nullable Level level, List<Component> tooltip, TooltipFlag flag) {
		tooltip.add(Component.translatable(hintKey).withStyle(ChatFormatting.GRAY, ChatFormatting.ITALIC));
	}
}
