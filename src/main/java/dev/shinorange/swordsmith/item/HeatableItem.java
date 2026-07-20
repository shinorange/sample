package dev.shinorange.swordsmith.item;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.HeatData;
import dev.shinorange.swordsmith.core.QualityData;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItems;
import java.util.List;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EquipmentSlot;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.item.tooltip.TooltipType;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import net.minecraft.world.World;

/**
 * A workpiece that carries heat. Its temperature decays lazily (Newton cooling);
 * once a second, while in an inventory, the stored snapshot is refreshed so the
 * tooltip and heat gauge stay accurate — and bare hands get burned. Holding
 * smithing tongs in either hand protects you, wearing the tongs down instead.
 */
public class HeatableItem extends Item {
	private final String hintKey;

	public HeatableItem(String hintKey, Settings settings) {
		super(settings);
		this.hintKey = hintKey;
	}

	@Override
	public void inventoryTick(ItemStack stack, World world, Entity entity, int slot, boolean selected) {
		if (world.isClient) {
			return;
		}
		if (world.getTime() % 20 != 0) {
			return;
		}
		HeatData data = stack.get(ModComponents.HEAT);
		if (data == null) {
			return;
		}
		float temp = Heat.current(world, stack);
		Heat.set(world, stack, temp);
		if (temp < Heat.BURN_TEMP || !(entity instanceof PlayerEntity player)) {
			return;
		}
		if (player.isCreative() || player.isSpectator()) {
			return;
		}
		ItemStack main = player.getMainHandStack();
		ItemStack off = player.getOffHandStack();
		if (main.isOf(ModItems.SMITHING_TONGS)) {
			main.damage(1, player, EquipmentSlot.MAINHAND);
		} else if (off.isOf(ModItems.SMITHING_TONGS)) {
			off.damage(1, player, EquipmentSlot.OFFHAND);
		} else {
			player.damage(world.getDamageSources().inFire(), 1.0f);
			player.sendMessage(Text.translatable("msg.swordsmith.too_hot_to_hold"), true);
		}
	}

	@Override
	public void appendTooltip(ItemStack stack, TooltipContext context, List<Text> tooltip, TooltipType type) {
		HeatData data = stack.get(ModComponents.HEAT);
		float temp = data == null ? Heat.AMBIENT : data.temperature();
		tooltip.add(Text.translatable("tooltip.swordsmith.temperature", (int) temp, Heat.label(temp)));
		Integer grind = stack.get(ModComponents.GRIND_PROGRESS);
		if (grind != null && grind > 0) {
			tooltip.add(Text.translatable("tooltip.swordsmith.grind", grind, Heat.GRIND_USES).formatted(Formatting.AQUA));
		}
		QualityData quality = stack.get(ModComponents.QUALITY);
		if (quality != null && quality.strikes() > 0) {
			tooltip.add(Text.translatable("tooltip.swordsmith.craft",
					Math.round(quality.strikeAverage() * 100f)).formatted(Formatting.YELLOW));
		}
		if (quality != null && quality.quenchScore() > 0f) {
			tooltip.add(Text.translatable("tooltip.swordsmith.quench_quality",
					Math.round(quality.quenchScore() * 100f)).formatted(Formatting.AQUA));
		}
		tooltip.add(Text.translatable(hintKey).formatted(Formatting.GRAY, Formatting.ITALIC));
	}

	@Override
	public boolean isItemBarVisible(ItemStack stack) {
		HeatData data = stack.get(ModComponents.HEAT);
		return data != null && data.temperature() > Heat.COLD_WORK_MAX;
	}

	@Override
	public int getItemBarStep(ItemStack stack) {
		HeatData data = stack.get(ModComponents.HEAT);
		return data == null ? 0 : Heat.barStep(data.temperature());
	}

	@Override
	public int getItemBarColor(ItemStack stack) {
		HeatData data = stack.get(ModComponents.HEAT);
		return Heat.barColor(data == null ? Heat.AMBIENT : data.temperature());
	}
}
