package dev.shinorange.swordsmith.menu;

import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.world.Container;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerData;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/**
 * The forge menu: slot 0 workpiece, slot 1 fuel, plus live gauges synced via
 * ContainerData. Taking the workpiece out through the GUI stamps its live
 * temperature — hot metal stays hot.
 */
public class ForgeMenu extends AbstractContainerMenu {
	private final Container container;
	private final ContainerData data;

	public ForgeMenu(int id, Inventory playerInventory) {
		this(id, playerInventory, new SimpleContainer(ForgeBlockEntity.SLOT_COUNT),
				new SimpleContainerData(ForgeBlockEntity.PROPERTY_COUNT));
	}

	public ForgeMenu(int id, Inventory playerInventory, Container container, ContainerData data) {
		super(ModRegistry.FORGE_MENU.get(), id);
		checkContainerSize(container, ForgeBlockEntity.SLOT_COUNT);
		this.container = container;
		this.data = data;
		container.startOpen(playerInventory.player);

		this.addSlot(new Slot(container, ForgeBlockEntity.SLOT_WORKPIECE, 80, 35) {
			@Override
			public boolean mayPlace(ItemStack stack) {
				return Smithing.isHeatable(stack);
			}

			@Override
			public int getMaxStackSize() {
				return 1;
			}

			@Override
			public void onTake(Player player, ItemStack stack) {
				if (container instanceof ForgeBlockEntity forge) {
					forge.stampHeat(stack);
				}
				super.onTake(player, stack);
			}
		});
		this.addSlot(new Slot(container, ForgeBlockEntity.SLOT_FUEL, 28, 53) {
			@Override
			public boolean mayPlace(ItemStack stack) {
				return stack.is(Items.COAL) || stack.is(Items.CHARCOAL);
			}
		});

		for (int row = 0; row < 3; row++) {
			for (int col = 0; col < 9; col++) {
				this.addSlot(new Slot(playerInventory, col + row * 9 + 9, 8 + col * 18, 84 + row * 18));
			}
		}
		for (int col = 0; col < 9; col++) {
			this.addSlot(new Slot(playerInventory, col, 8 + col * 18, 142));
		}

		this.addDataSlots(data);
	}

	public int getFireTemp() {
		return data.get(ForgeBlockEntity.PROPERTY_FIRE_TEMP);
	}

	public int getWorkTemp() {
		return data.get(ForgeBlockEntity.PROPERTY_WORK_TEMP);
	}

	public int getFuelSeconds() {
		return data.get(ForgeBlockEntity.PROPERTY_FUEL_SECONDS);
	}

	public int getAirflowPercent() {
		return data.get(ForgeBlockEntity.PROPERTY_AIRFLOW);
	}

	public int getProgressPercent() {
		return data.get(ForgeBlockEntity.PROPERTY_PROGRESS);
	}

	public ItemStack getWorkpiece() {
		return container.getItem(ForgeBlockEntity.SLOT_WORKPIECE);
	}

	@Override
	public ItemStack quickMoveStack(Player player, int index) {
		ItemStack result = ItemStack.EMPTY;
		Slot slot = this.slots.get(index);
		if (slot.hasItem()) {
			ItemStack original = slot.getItem();
			result = original.copy();
			if (index < ForgeBlockEntity.SLOT_COUNT) {
				if (!this.moveItemStackTo(original, ForgeBlockEntity.SLOT_COUNT, 38, true)) {
					return ItemStack.EMPTY;
				}
			} else if (original.is(Items.COAL) || original.is(Items.CHARCOAL)) {
				if (!this.moveItemStackTo(original, ForgeBlockEntity.SLOT_FUEL, ForgeBlockEntity.SLOT_FUEL + 1, false)) {
					return ItemStack.EMPTY;
				}
			} else if (Smithing.isHeatable(original)) {
				if (!this.moveItemStackTo(original, ForgeBlockEntity.SLOT_WORKPIECE, ForgeBlockEntity.SLOT_WORKPIECE + 1, false)) {
					return ItemStack.EMPTY;
				}
			} else if (index < 29) {
				if (!this.moveItemStackTo(original, 29, 38, false)) {
					return ItemStack.EMPTY;
				}
			} else if (!this.moveItemStackTo(original, 2, 29, false)) {
				return ItemStack.EMPTY;
			}

			if (original.isEmpty()) {
				slot.setByPlayer(ItemStack.EMPTY);
			} else {
				slot.setChanged();
			}
			if (original.getCount() == result.getCount()) {
				return ItemStack.EMPTY;
			}
			slot.onTake(player, original);
		}
		return result;
	}

	@Override
	public boolean stillValid(Player player) {
		return this.container.stillValid(player);
	}

	@Override
	public void removed(Player player) {
		super.removed(player);
		this.container.stopOpen(player);
	}
}
