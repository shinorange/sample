package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.QualityData;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.ItemUsage;
import net.minecraft.item.Items;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvents;
import net.minecraft.state.StateManager;
import net.minecraft.state.property.BooleanProperty;
import net.minecraft.text.Text;
import net.minecraft.util.Hand;
import net.minecraft.util.ItemActionResult;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

/**
 * A water-filled quenching tub. Plunge a rough blade in at cherry-red heat
 * (780-950 C) to harden it into a quenched blade. Hotter than that and the
 * thermal shock cracks it; cooler and no hardness forms. Any other glowing
 * workpiece can be dunked simply to cool it off.
 */
public class QuenchingBarrelBlock extends Block {
	public static final BooleanProperty FILLED = BooleanProperty.of("filled");

	public QuenchingBarrelBlock(Settings settings) {
		super(settings);
		this.setDefaultState(this.getDefaultState().with(FILLED, false));
	}

	@Override
	protected void appendProperties(StateManager.Builder<Block, BlockState> builder) {
		builder.add(FILLED);
	}

	@Override
	protected ItemActionResult onUseWithItem(ItemStack stack, BlockState state, World world, BlockPos pos, PlayerEntity player, Hand hand, BlockHitResult hit) {
		boolean filled = state.get(FILLED);

		if (stack.isOf(Items.WATER_BUCKET)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			if (!filled) {
				world.setBlockState(pos, state.with(FILLED, true), Block.NOTIFY_ALL);
				player.setStackInHand(hand, ItemUsage.exchangeStack(stack, player, new ItemStack(Items.BUCKET)));
				world.playSound(null, pos, SoundEvents.ITEM_BUCKET_EMPTY, SoundCategory.BLOCKS, 1.0f, 1.0f);
			} else {
				player.sendMessage(Text.translatable("msg.swordsmith.barrel_full"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		if (!Smithing.isHeatable(stack)) {
			return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
		}

		if (!filled) {
			if (!world.isClient) {
				player.sendMessage(Text.translatable("msg.swordsmith.barrel_empty"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		if (world.isClient) {
			return ItemActionResult.SUCCESS;
		}

		float temp = Heat.current(world, stack);

		// The hardening quench itself.
		if (stack.isOf(ModItems.ROUGH_BLADE)) {
			if (temp >= Heat.QUENCH_MIN && temp <= Heat.QUENCH_MAX) {
				ItemStack quenched = new ItemStack(ModItems.QUENCHED_BLADE);
				Quality.carry(stack, quenched);
				QualityData data = quenched.getOrDefault(ModComponents.QUALITY, QualityData.EMPTY);
				quenched.set(ModComponents.QUALITY, data.withQuench(Quality.quenchScore(temp)));
				player.setStackInHand(hand, quenched);
				player.sendMessage(Text.translatable("msg.swordsmith.quench_ok"), true);
				hiss(world, pos, 1.0f);
			} else if (temp > Heat.QUENCH_MAX) {
				ItemStack cracked = new ItemStack(ModItems.CRACKED_BLADE);
				Quality.carry(stack, cracked);
				player.setStackInHand(hand, cracked);
				player.sendMessage(Text.translatable("msg.swordsmith.quench_crack"), true);
				world.playSound(null, pos, SoundEvents.ENTITY_ITEM_BREAK, SoundCategory.BLOCKS, 1.0f, 0.8f);
				hiss(world, pos, 1.0f);
			} else if (temp > Heat.COLD_WORK_MAX) {
				Heat.set(world, stack, Heat.AMBIENT);
				player.sendMessage(Text.translatable("msg.swordsmith.quench_weak"), true);
				hiss(world, pos, 0.6f);
			} else {
				player.sendMessage(Text.translatable("msg.swordsmith.quench_cold"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		// Anything else just gets cooled off.
		if (temp > Heat.COLD_WORK_MAX) {
			Heat.set(world, stack, Heat.AMBIENT);
			hiss(world, pos, 0.7f);
		}
		return ItemActionResult.SUCCESS;
	}

	private void hiss(World world, BlockPos pos, float volume) {
		world.playSound(null, pos, SoundEvents.BLOCK_LAVA_EXTINGUISH, SoundCategory.BLOCKS, volume, 1.0f);
		if (world instanceof ServerWorld serverWorld) {
			serverWorld.spawnParticles(ParticleTypes.CLOUD,
					pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 10, 0.2, 0.1, 0.2, 0.02);
			serverWorld.spawnParticles(ParticleTypes.SPLASH,
					pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, 8, 0.25, 0.05, 0.25, 0.1);
		}
	}
}
