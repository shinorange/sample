package dev.shinorange.swordsmith.block.entity;

import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.block.entity.BlockEntityType;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.nbt.NbtCompound;
import net.minecraft.network.listener.ClientPlayPacketListener;
import net.minecraft.network.packet.Packet;
import net.minecraft.network.packet.s2c.play.BlockEntityUpdateS2CPacket;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.registry.RegistryWrapper;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvents;
import net.minecraft.text.Text;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

/**
 * Simulates the fire: fuel burns down, bellows air raises the target
 * temperature, and the workpiece asymptotically approaches the fire's
 * temperature. Two slow transformations happen in the coals:
 *
 * - bloomery smelting: raw iron held above 1150 C becomes an iron bloom
 * - tempering: a quenched blade held at 150-400 C becomes a tempered blade,
 *   but above 460 C the hardness is lost again (annealed back to a rough blade)
 */
public class ForgeBlockEntity extends BlockEntity {
	private static final float MAX_FUEL_SECONDS = 300f;
	private static final float FUEL_SECONDS_PER_COAL = 60f;

	private ItemStack workpiece = ItemStack.EMPTY;
	private float fuelSeconds;
	private float airflow;
	private float forgeTemp = Heat.AMBIENT;
	private float workTemp = Heat.AMBIENT;
	private int smeltProgress;
	private int temperProgress;

	public ForgeBlockEntity(BlockPos pos, BlockState state) {
		super(ModBlockEntities.FORGE, pos, state);
	}

	public static void serverTick(World world, BlockPos pos, BlockState state, ForgeBlockEntity forge) {
		boolean lit = state.get(ForgeBlock.LIT);
		float target = lit ? Heat.FORGE_BASE_TEMP + forge.airflow * Heat.BELLOWS_BONUS : Heat.AMBIENT;
		forge.forgeTemp += (target - forge.forgeTemp) * 0.005f;
		forge.airflow = Math.max(0f, forge.airflow - 1f / 400f);

		if (lit) {
			forge.fuelSeconds -= (1f + forge.airflow) / 20f;
			if (forge.fuelSeconds <= 0f) {
				forge.fuelSeconds = 0f;
				world.setBlockState(pos, state.with(ForgeBlock.LIT, false), Block.NOTIFY_ALL);
			}
		}

		if (!forge.workpiece.isEmpty()) {
			forge.workTemp += (forge.forgeTemp - forge.workTemp) * 0.02f;
			forge.tickTransformations(world, pos);
		} else {
			forge.workTemp = forge.forgeTemp;
		}

		if (world.getTime() % 20 == 0) {
			forge.markDirty();
		}
	}

	private void tickTransformations(World world, BlockPos pos) {
		if (workpiece.isOf(Items.RAW_IRON)) {
			if (workTemp >= Heat.SMELT_TEMP) {
				if (++smeltProgress >= Heat.SMELT_TICKS) {
					workpiece = new ItemStack(ModItems.IRON_BLOOM);
					smeltProgress = 0;
					world.playSound(null, pos, SoundEvents.BLOCK_LAVA_POP, SoundCategory.BLOCKS, 1.0f, 0.8f);
					if (world instanceof ServerWorld serverWorld) {
						serverWorld.spawnParticles(ParticleTypes.LAVA,
								pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 8, 0.2, 0.1, 0.2, 0.0);
					}
					markDirtyAndSync();
				}
			} else if (smeltProgress > 0) {
				smeltProgress--;
			}
		} else if (workpiece.isOf(ModItems.QUENCHED_BLADE)) {
			if (workTemp > Heat.ANNEAL_TEMP) {
				// Too hot: the quench hardness is annealed away.
				workpiece = new ItemStack(ModItems.ROUGH_BLADE);
				temperProgress = 0;
				world.playSound(null, pos, SoundEvents.BLOCK_FIRE_EXTINGUISH, SoundCategory.BLOCKS, 0.8f, 0.5f);
				if (world instanceof ServerWorld serverWorld) {
					serverWorld.spawnParticles(ParticleTypes.SMOKE,
							pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, 12, 0.2, 0.1, 0.2, 0.02);
				}
				markDirtyAndSync();
			} else if (workTemp >= Heat.TEMPER_MIN && workTemp <= Heat.TEMPER_MAX) {
				if (++temperProgress >= Heat.TEMPER_TICKS) {
					workpiece = new ItemStack(ModItems.TEMPERED_BLADE);
					temperProgress = 0;
					world.playSound(null, pos, SoundEvents.ENTITY_EXPERIENCE_ORB_PICKUP, SoundCategory.BLOCKS, 0.7f, 1.2f);
					markDirtyAndSync();
				}
			}
		}
	}

	public boolean addFuel() {
		if (fuelSeconds >= MAX_FUEL_SECONDS - 1f) {
			return false;
		}
		fuelSeconds = Math.min(MAX_FUEL_SECONDS, fuelSeconds + FUEL_SECONDS_PER_COAL);
		markDirty();
		return true;
	}

	public boolean hasFuel() {
		return fuelSeconds > 0f;
	}

	public void pump() {
		airflow = Math.min(1f, airflow + 0.34f);
		markDirty();
	}

	public ItemStack getWorkpiece() {
		return workpiece;
	}

	public void insertWorkpiece(ItemStack stack) {
		workpiece = stack;
		workTemp = world != null ? Heat.current(world, stack) : Heat.AMBIENT;
		smeltProgress = 0;
		temperProgress = 0;
		markDirtyAndSync();
	}

	/** Removes the workpiece, stamping its current temperature onto the stack. */
	public ItemStack takeWorkpiece() {
		ItemStack out = workpiece;
		workpiece = ItemStack.EMPTY;
		smeltProgress = 0;
		temperProgress = 0;
		if (world != null && !out.isEmpty()) {
			Heat.set(world, out, workTemp);
		}
		markDirtyAndSync();
		return out;
	}

	public void sendStatus(PlayerEntity player) {
		player.sendMessage(Text.translatable("msg.swordsmith.forge_status",
				(int) forgeTemp, (int) fuelSeconds, (int) (airflow * 100f)), true);
	}

	private void markDirtyAndSync() {
		markDirty();
		if (world != null) {
			world.updateListeners(pos, getCachedState(), getCachedState(), Block.NOTIFY_LISTENERS);
		}
	}

	@Override
	public void writeNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.writeNbt(nbt, registryLookup);
		if (!workpiece.isEmpty()) {
			nbt.put("Workpiece", workpiece.encode(registryLookup));
		}
		nbt.putFloat("Fuel", fuelSeconds);
		nbt.putFloat("Airflow", airflow);
		nbt.putFloat("ForgeTemp", forgeTemp);
		nbt.putFloat("WorkTemp", workTemp);
		nbt.putInt("SmeltProgress", smeltProgress);
		nbt.putInt("TemperProgress", temperProgress);
	}

	@Override
	public void readNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.readNbt(nbt, registryLookup);
		workpiece = nbt.contains("Workpiece")
				? ItemStack.fromNbt(registryLookup, nbt.getCompound("Workpiece")).orElse(ItemStack.EMPTY)
				: ItemStack.EMPTY;
		fuelSeconds = nbt.getFloat("Fuel");
		airflow = nbt.getFloat("Airflow");
		forgeTemp = nbt.getFloat("ForgeTemp");
		workTemp = nbt.getFloat("WorkTemp");
		smeltProgress = nbt.getInt("SmeltProgress");
		temperProgress = nbt.getInt("TemperProgress");
	}

	@Override
	public Packet<ClientPlayPacketListener> toUpdatePacket() {
		return BlockEntityUpdateS2CPacket.create(this);
	}

	@Override
	public NbtCompound toInitialChunkDataNbt(RegistryWrapper.WrapperLookup registryLookup) {
		return createNbt(registryLookup);
	}
}
