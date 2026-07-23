package dev.shinorange.swordsmith.screen;

import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModScreenHandlers;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.entity.player.PlayerInventory;
import net.minecraft.inventory.Inventory;
import net.minecraft.inventory.SimpleInventory;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.screen.ArrayPropertyDelegate;
import net.minecraft.screen.PropertyDelegate;
import net.minecraft.screen.ScreenHandler;
import net.minecraft.screen.slot.Slot;

/**
 * The forge menu: slot 0 workpiece, slot 1 fuel, plus live gauges (fire and
 * workpiece temperature, fuel seconds, bellows blast, smelt/temper progress)
 * synced through a {@link PropertyDelegate}. Taking the workpiece out through
 * the GUI stamps its current temperature — hot metal stays hot.
 */
public class ForgeScreenHandler extends ScreenHandler {
	private final Inventory inventory;
	private final PropertyDelegate propertyDelegate;

	public ForgeScreenHandler(int syncId, PlayerInventory playerInventory) {
		this(syncId, playerInventory, new SimpleInventory(ForgeBlockEntity.SLOT_COUNT),
				new ArrayPropertyDelegate(ForgeBlockEntity.PROPERTY_COUNT));
	}

	public ForgeScreenHandler(int syncId, PlayerInventory playerInventory, Inventory inventory, PropertyDelegate propertyDelegate) {
		super(ModScreenHandlers.FORGE, syncId);
		checkSize(inventory, ForgeBlockEntity.SLOT_COUNT);
		this.inventory = inventory;
		this.propertyDelegate = propertyDelegate;
		inventory.onOpen(playerInventory.player);

		this.addSlot(new Slot(inventory, ForgeBlockEntity.SLOT_WORKPIECE, 80, 35) {
			@Override
			public boolean canInsert(ItemStack stack) {
				return Smithing.isHeatable(stack);
			}

			@Override
			public int getMaxItemCount() {
				return 1;
			}

			@Override
			public void onTakeItem(PlayerEntity player, ItemStack stack) {
				if (inventory instanceof ForgeBlockEntity forge) {
					forge.stampHeat(stack);
				}
				super.onTakeItem(player, stack);
			}
		});
		this.addSlot(new Slot(inventory, ForgeBlockEntity.SLOT_FUEL, 28, 53) {
			@Override
			public boolean canInsert(ItemStack stack) {
				return stack.isOf(Items.COAL) || stack.isOf(Items.CHARCOAL);
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

		this.addProperties(propertyDelegate);
	}

	public int getFireTemp() {
		return propertyDelegate.get(ForgeBlockEntity.PROPERTY_FIRE_TEMP);
	}

	public int getWorkTemp() {
		return propertyDelegate.get(ForgeBlockEntity.PROPERTY_WORK_TEMP);
	}

	public int getFuelSeconds() {
		return propertyDelegate.get(ForgeBlockEntity.PROPERTY_FUEL_SECONDS);
	}

	public int getAirflowPercent() {
		return propertyDelegate.get(ForgeBlockEntity.PROPERTY_AIRFLOW);
	}

	public int getProgressPercent() {
		return propertyDelegate.get(ForgeBlockEntity.PROPERTY_PROGRESS);
	}

	public ItemStack getWorkpiece() {
		return inventory.getStack(ForgeBlockEntity.SLOT_WORKPIECE);
	}

	@Override
	public ItemStack quickMove(PlayerEntity player, int index) {
		ItemStack result = ItemStack.EMPTY;
		Slot slot = this.slots.get(index);
		if (slot != null && slot.hasStack()) {
			ItemStack original = slot.getStack();
			result = original.copy();
			if (index < ForgeBlockEntity.SLOT_COUNT) {
				if (!this.insertItem(original, ForgeBlockEntity.SLOT_COUNT, 38, true)) {
					return ItemStack.EMPTY;
				}
			} else if (original.isOf(Items.COAL) || original.isOf(Items.CHARCOAL)) {
				if (!this.insertItem(original, ForgeBlockEntity.SLOT_FUEL, ForgeBlockEntity.SLOT_FUEL + 1, false)) {
					return ItemStack.EMPTY;
				}
			} else if (Smithing.isHeatable(original)) {
				if (!this.insertItem(original, ForgeBlockEntity.SLOT_WORKPIECE, ForgeBlockEntity.SLOT_WORKPIECE + 1, false)) {
					return ItemStack.EMPTY;
				}
			} else if (index < 29) {
				if (!this.insertItem(original, 29, 38, false)) {
					return ItemStack.EMPTY;
				}
			} else if (!this.insertItem(original, 2, 29, false)) {
				return ItemStack.EMPTY;
			}

			if (original.isEmpty()) {
				slot.setStack(ItemStack.EMPTY);
			} else {
				slot.markDirty();
			}
			if (original.getCount() == result.getCount()) {
				return ItemStack.EMPTY;
			}
			slot.onTakeItem(player, original);
		}
		return result;
	}

	@Override
	public boolean canUse(PlayerEntity player) {
		return this.inventory.canPlayerUse(player);
	}

	@Override
	public void onClosed(PlayerEntity player) {
		super.onClosed(player);
		this.inventory.onClose(player);
	}
}
