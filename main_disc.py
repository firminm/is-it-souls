from collections import UserString
from discord.embeds import Embed
from discord.errors import Forbidden
import pymongo, discord, os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN       = os.getenv('token')
client      = os.getenv('client')
db_client   = pymongo.MongoClient(client)
DB          = db_client['steamData']
APPDATA     = DB['appData']
GUILDS      = DB['guilds']
USERS       = DB['users']
SUGGS       = DB['suggests']


'''    Setting Up/Initializeing Bot    '''
PREFIX = '$'
def get_prefix(bot, message):
    return PREFIX

intents = discord.Intents.default()
intents.members = True  # Subscribe to the privileged members intent.

bot = commands.Bot(command_prefix=(get_prefix), intents=intents )
# bot.remove_command('help')    TODO: Un-comment once help page is implemented

@bot.event
async def on_guild_join(guild):
    pass

@bot.event
async def on_guild_remove(guild):
    pass

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))


'''    --------------------  Begin interactive commands tracking  (bot commands)--------------------    '''


@bot.command(pass_context=True)
async def souls(ctx, *args, appID=None):
    """
    Main feature of bot, sends a link to a steam game and allows users to vote yes/no via reactions.
    Takes a game name as argument

    React with:
      ✅ to vote yes 
      ❌ to vote no
      📰 to see results

    Required Permissions:
      - send_messages
      - add_reactions
      - manage_messages
    """
    if appID is not None:
        # Accessed when called from @add
        doc = APPDATA.find_one({'_id': appID})

    elif args is None or len(args) == 0:
        doc = APPDATA.aggregate([{'$sample': {'size': 1}}])
        doc = list(doc)
        doc = doc[0]

    else:
        join = ' '.join(args)
        doc = APPDATA.find_one({'title': {'$regex': join, '$options': 'i'}})
        if doc is None:
            await ctx.channel.send(f"Game could not be found, try adding it with `{PREFIX}add {join}`")
            return

    # doc now holds the document/information of a random game
    if doc['desc'] is None or doc['desc'] == "":
        # Check if game is missing description value
        desc = '\u2008'
    else:
        desc = doc['desc']

    emb = discord.Embed(title=doc['title'], description=desc)#, url=doc['storePage'])
    emb.set_author(name='Is it Souls-Like?', url=doc['storePage'])
    emb.set_image(url=doc['thumbnail'])
    # emb.set_footer(text=f'React with 📔 to skip voting and see results')
    emb.set_footer(text=doc['_id'])
    # emb.add_field(name='Is it Souls-Like?', value=doc['desc'])
    
    msg = await ctx.channel.send(embed=emb)
    await msg.add_reaction('✅')
    await msg.add_reaction('❌')
    await msg.add_reaction('📰')


@bot.command(pass_context=True)
async def add(ctx, *args):
    """
    Takes steam app ID as a paramter, adds steam game to souls database
    DOES NOT TAKE LINKS OR TITLES
    """
    try:
        app_id = int(args[0])
    except (ValueError, IndexError):
        await ctx.channel.send(f'❌Invalid App ID, type `{PREFIX}help appid` for information about valid app IDs')
        return


    # Check to see if application already exists in the game (avoids suggestion of apps that have already been added)
    app = APPDATA.find_one({'_id': app_id})
    if app is not None:
        # Application already being used in game
        await ctx.channel.send(f"Application {app['title']} (ID {app_id}) already added")
        return
    
    app = SUGGS.find_one({'_id': app_id})
    if app is None:
        SUGGS.insert_one({'_id': app_id, 'user': [ctx.author.id], 'added': False})
        await ctx.channel.send(f"✅Application suggested successfully")
    else:
        SUGGS.update_one({'_id': app_id}, {'$addToSet': {'users': ctx.author.id}})
        await ctx.channel.send(f"Application already suggested")



''' --------------- Bot Interactions (bot events)---------------'''


@bot.event
async def on_reaction_add(reaction, user):
    """
    Affects $souls command
    React with:
      ✅ to vote yes 
      ❌ to vote no
      📰 to see results

    Permissions Required:
      - manage_messages
    """
    if user != bot.user and reaction.message.author == bot.user and reaction.message.embeds[0].footer != discord.Embed.Empty:
        # if the reaction was not created by the bot && the message was created by the bot && the footer is not empty
        app_id  = reaction.message.embeds[0].footer.text
        app     = APPDATA.find_one({'_id': app_id})
        user_id    = user.id
        user_doc = USERS.find_one({'_id': user_id})
        if user_doc is None:
            USERS.insert_one({'_id': user_id, 'guilds': [reaction.message.channel.guild.id], 'vote': {}})
            user_doc = USERS.find_one({'_id': user_id})
            vote = None
        try:
            vote = user_doc['vote'][app_id]
        except KeyError:
            vote = None
        
        zero = False
        one  = True
        if reaction.emoji == '✅' and vote != one:
            # vote != 1 prevents double-counting
            if vote == zero:
                # Change-of-confidence vote. First remove the old vote
                try: 
                    # Requires permissions.manage_messages
                    # on_reaction_remove() triggered by the below expression, which will decrement the appropriate field
                    member = reaction.message.channel.guild.get_member(user.id)
                    await reaction.message.remove_reaction('❌', member)   
                except Forbidden:
                    # Preserves DB integ In the event guild-owners decide not to give full range of permissions (happens a lot)
                    APPDATA.update_one({'_id': app_id}, {'$inc': {'notSouls': -1}})

            APPDATA.update_one({'_id': app_id}, {'$inc': {'souls': 1}})
            USERS.update_one({'_id': user_id}, {'$set': {f'vote.{app_id}': one}})

        elif reaction.emoji == '❌' and vote != zero:  
            # vote != 0 prevents double-counting
            if vote == one:
                # Change of conficdence vote (2 votes enabled at once), remove first vote
                try:
                    member = reaction.message.channel.guild.get_member(user.id)
                    await reaction.message.remove_reaction('✅', member)  
                except Forbidden:
                    APPDATA.update_one({'_id': app_id}, {'$inc': {'souls': -1}})

                
            APPDATA.update_one({'_id': app_id}, {'$inc': {'notSouls': 1}})
            USERS.update_one({'_id': user_id}, {'$set': {f'vote.{app_id}': one}})

        elif reaction.emoji == '📰':
            total = app['souls'] + app['notSouls']
            if total == 0:  # div by 0 check
                pct_souls = 0
                pct_not_souls = 0
            else:
                pct_souls     = '%.0f%%' % (app['souls']/total * 100)
                pct_not_souls = '%.0f%%' % (app['notSouls']/total * 100)

            emb = reaction.message.embeds[0]
            emb.clear_fields()
            emb.add_field(name='Is Souls-Like', value=pct_souls)
            emb.add_field(name='Not Souls-Like', value=pct_not_souls, inline=True)
            emb.add_field(name='Total Votes', value=total)
            await reaction.message.edit(embed=emb)


        
@bot.event
async def on_reaction_remove(reaction, user):
    """
    When a reaction is removed from an @souls embed, update database (untrack vote)

    Requires permissions.manage_reactions
    Only called if intents.members is allowed
    """
    if user != bot.user and reaction.message.author == bot.user and reaction.message.embeds[0].footer != discord.Embed.Empty:
        # Ensures the reaction is on the correct message and bot reactions are not being counted
        app_id  = reaction.message.embeds[0].footer.text
        
        # Dealing with user-end is pretty easy, delete interaction regardless of type
        USERS.update_one({'_id': user.id}, {'$unset': {f'vote.{app_id}': ""}})

        # Update application-side
        if reaction.emoji == '✅':
            APPDATA.update_one({'_id': app_id}, {'$inc': {'souls': -1}})

        elif reaction.emoji == '❌':
            APPDATA.update_one({'_id': app_id}, {'$inc': {'notSouls': -1}})



'''    ---------------  Method Checks  ---------------    '''

    



bot.run(TOKEN)