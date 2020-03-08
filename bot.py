#!/usr/bin/env python3

import os, json, logging
from telegram.ext import CommandHandler, Updater, Filters, MessageHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def load_json(fn, default=None):
	if os.path.exists(fn):
		with open(fn) as fp:
			return json.load(fp)
	return default


def store_json(fn, data):
	with open(fn + '.tmp', 'w') as fp:
		json.dump(data, fp, indent=1, sort_keys=True)
	os.unlink(fn)
	os.rename(fn + '.tmp', fn)


class DispatchWrapper:
	def __init__(self, cmd, fun):
		(self._cmd, self._fun) = (cmd, fun)

	def __call__(self, update, ctx):
		user = update.message.from_user.username
		args = update.message.text.split(' ', 1)
		arg = ''
		if len(args) > 1:
			arg = args[-1]
		logging.info('Received command %s from %s: %s', self._cmd, user, repr(arg))
		return self._fun(update, ctx, arg=arg)


def fmt_num(value):
	if value == 0:
		return 'no'
	if value == 1:
		return '1st'
	if value == 2:
		return '2nd'
	if value == 3:
		return '3rd'
	return str(value) + 'th'


def staff_only(func):
	def fun_wrapper(self, update, ctx, arg):
		if self.check_staff(update, ctx):
			func(self, update, ctx, arg)
	return fun_wrapper


class LurkerAdminBot:
	def __init__(self):
		self._state_fn = 'bot_state.json'
		self._state = load_json(self._state_fn, {})
		self._state.setdefault('warnings', {})
		self._state.setdefault('bans', {})
		self._state.setdefault('custom', {})
		self._state.setdefault('staff', [])

	def check_staff(self, update, ctx):
		# admin_list = bot.get_chat_administrators(update.message.chat_id)
		if str(update.message.from_user.id) not in self._state['staff']:
			from_user = update.message.from_user
			self._msg_chat(update, ctx,
				f'{from_user.username} ({from_user.id}) is not staff and can\'t use this command!')
			return False
		return True

	def _msg_chat(self, update, ctx, msg):
		ctx.bot.send_message(chat_id=update.message.chat_id, text=msg)

	@staff_only
	def _warn(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
			warn_list = self._state['warnings'].setdefault(str(target_user.id), [])
			warn_list.append(arg)
			num_msg = fmt_num(len(warn_list))
			self._msg_chat(update, ctx, f'@{target_user.username}: {arg} (This is your {num_msg} warning!)')
			if len(warn_list) == 3:
				self._ban(update, ctx, 'The user got 3 warnings')

	@staff_only
	def _unwarn(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
			warn_list = self._state['warnings'].setdefault(str(target_user.id), [])
			if warn_list:
				warn_list.pop()
			num_msg = fmt_num(len(warn_list))
			self._msg_chat(update, ctx, f'@{target_user.username}: You have {num_msg} warnings now!')

	@staff_only
	def _nowarns(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
			self._state['warnings'].pop(str(target_user.id), None)
			self._msg_chat(update, ctx, f'@{target_user.username}: You have no warnings now!')

	@staff_only
	def _ban(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
			if str(target_user.id) in self._state['staff']:
				self._msg_chat(update, ctx, 'You can\'t ban a staff member!')
			else:
				self._state['bans'].setdefault(str(target_user.id), {'name': target_user.username})
				ctx.bot.kick_chat_member(update.message.chat_id, target_user.id)
				self._msg_chat(update, ctx, f'@{target_user.username} was banned: {arg}')

	@staff_only
	def _unban(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
			self._state['bans'].pop(str(target_user.id), None)
			ctx.bot.unban_chat_member(update.message.chat_id, target_user.id)
			self._msg_chat(update, ctx, f'@{target_user.username} was unbanned!')

	def _user(self, update, ctx, arg):
		if update.message.reply_to_message:
			target_user = update.message.reply_to_message.from_user
		else:
			target_user = update.message.from_user
		msg = f'Status for @{target_user.username} ({target_user.id}):\n'
		if str(target_user.id) in self._state['bans']:
			msg += '\tUser is BANNED!\n'
		for idx, warning in enumerate(self._state['warnings'].get(str(target_user.id), [])):
			msg += f'\tWarning #{idx + 1}: {warning}\n'
		self._msg_chat(update, ctx, msg)

	def _staff(self, update, ctx, arg):
		msg = 'List of staff:\n'
		for staff_id in self._state['staff']:
			try:
				staff_user = ctx.bot.get_chat_member(update.message.chat_id, int(staff_id))
				msg += f'@{staff_user.user.username}\n'
			except Exception:
				msg += f'{staff_id} (not in this chat)\n'
		self._msg_chat(update, ctx, msg)

	def _report(self, update, ctx, arg):
		for staff_id in self._state['staff']:
			ctx.bot.send_message(chat_id=int(staff_id),
				text=f'Message was reported by {update.message.from_user.username} in {update.message.chat.title}!')
			if update.message.reply_to_message:
				ctx.bot.forward_message(chat_id=staff_id, from_chat_id=update.message.chat_id,
					message_id=update.message.message_id)

	@staff_only
	def _addcommand(self, update, ctx, arg):
		args = arg.split(' ', 1)
		if len(args) == 2:
			custom_cmd = args[0]
			custom_msg = args[1]
			self._state['custom'][custom_cmd] = custom_msg
			self._msg_chat(update, ctx, f'New custom command {custom_cmd} defined: {custom_msg}')
		else:
			self._msg_chat(update, ctx, f'New custom command {custom_cmd} defined: {custom_msg}')

	@staff_only
	def _removecommand(self, update, ctx, arg):
		if self._state['custom'].pop(arg, None) is None:
			self._msg_chat(update, ctx, f'Command {arg} not found!')
		else:
			self._msg_chat(update, ctx, f'Command {arg} removed!')

	def _help(self, update, ctx, arg):
		ctx.bot.send_message(chat_id=update.message.chat_id, text="""
/warn <reason> - Warns the user.
/unwarn - Removes the last warn from the user.
/nowarns - Clears warns for the user.
/ban <reason> - Bans the user from groups.
/unban - Removes the user from ban list.
/user - Shows user's status and warns.
/addcommand <name> - to create a custom command.
/removecommand <name> - to remove a custom command.

Commands for everyone:
/staff - Shows a list of admins.
/report - Reports the replied-to message to admins.
""")

	def _on_message(self, update, ctx):
		msg = update.message.text
		if msg.startswith('!'):
			cmd = msg.lstrip('!').split()[0]
			custom = self._state['custom'].get(cmd, None)
			if custom:
				self._msg_chat(update, ctx, custom)

	def error(self, update, ctx):
		logging.warning('Update "%s" caused error "%s"', update, ctx.error)

	def start(self):
		logging.info('Setting up bot...')
		updater = Updater(token=load_json('telegram_token.json')[0], use_context=True)
		command_list = [
			('help', self._help),
			('warn', self._warn), ('unwarn', self._unwarn), ('nowarns', self._nowarns),
			('ban', self._ban), ('unban', self._unban),
			('addcommand', self._addcommand), ('removecommand', self._removecommand),
			('user', self._user),
			('staff', self._staff),
			('report', self._report),
		]
		for cmd, fun in command_list:
			updater.dispatcher.add_handler(CommandHandler(cmd, DispatchWrapper(cmd, fun)))
		updater.dispatcher.add_error_handler(self.error)
		updater.dispatcher.add_handler(MessageHandler(Filters.all, self._on_message))
		logging.info('Starting bot...')
		updater.start_polling()
		updater.idle()
		logging.info('Shutting down bot...')
		store_json(self._state_fn, self._state)


if __name__ == '__main__':
	LurkerAdminBot().start()
