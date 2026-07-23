package dev.shinorange.swordsmith.item;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.registry.ModRegistry;
import java.util.List;
import javax.annotation.Nullable;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;

/**
 * A workpiece that carries heat in NBT. Once a second in an inventory the
 * stored snapshot is refreshed (so tooltip and gauge stay honest) and bare
 * hands get burned — smithing tongs in either hand absorb the damage instead.
 */
public class HeatableItem extends Item {
	private final String hintKey;

	public HeatableItem(String hintKey, Properties properties) {
		super(properties);
		this.hintKey = hintKey;
	}

	@Override
	public void inventoryTick(ItemStack stack, Level level, Entity entity, int slot, boolean selected) {
		if (level.isClientSide || level.getGameTime() % 20 != 0 || !Heat.hasHeat(stack)) {
			return;
		}
		float temp = Heat.current(level, stack);
		Heat.set(level, stack, temp);
		if (temp < Heat.BURN_TEMP || !(entity instanceof Player player)) {
			return;
		}
		if (player.isCreative() || player.isSpectator()) {
			return;
		}
		ItemStack main = player.getMainHandItem();
		ItemStack off = player.getOffhandItem();
		if (main.is(ModRegistry.SMITHING_TONGS.get())) {
			main.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(EquipmentSlot.MAINHAND));
		} else if (off.is(ModRegistry.SMITHING_TONGS.get())) {
			off.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(EquipmentSlot.OFFHAND));
		} else {
			player.hurt(level.damageSources().inFire(), 1.0f);
			player.displayClientMessage(Component.translatable("msg.swordsmith.too_hot_to_hold"), true);
		}
	}

	@Override
	public void appendHoverText(ItemStack stack, @Nullable Level level, List<Component> tooltip, TooltipFlag flag) {
		float temp = Heat.raw(stack);
		tooltip.add(Component.translatable("tooltip.swordsmith.temperature", (int) temp, Heat.label(temp)));
		int grind = stack.getTag() == null ? 0 : stack.getTag().getInt(Quality.GRIND_KEY);
		if (grind > 0) {
			tooltip.add(Component.translatable("tooltip.swordsmith.grind", grind, Heat.GRIND_USES)
					.withStyle(ChatFormatting.AQUA));
		}
		if (Quality.strikeCount(stack) > 0) {
			tooltip.add(Component.translatable("tooltip.swordsmith.craft",
					Math.round(Quality.strikeAverage(stack) * 100f)).withStyle(ChatFormatting.YELLOW));
		}
		if (Quality.quenchValue(stack) > 0f) {
			tooltip.add(Component.translatable("tooltip.swordsmith.quench_quality",
					Math.round(Quality.quenchValue(stack) * 100f)).withStyle(ChatFormatting.AQUA));
		}
		tooltip.add(Component.translatable(hintKey).withStyle(ChatFormatting.GRAY, ChatFormatting.ITALIC));
	}

	@Override
	public boolean isBarVisible(ItemStack stack) {
		return Heat.hasHeat(stack) && Heat.raw(stack) > Heat.COLD_WORK_MAX;
	}

	@Override
	public int getBarWidth(ItemStack stack) {
		return Heat.barWidth(Heat.raw(stack));
	}

	@Override
	public int getBarColor(ItemStack stack) {
		return Heat.barColor(Heat.raw(stack));
	}
}
