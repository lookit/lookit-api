import os

from django.contrib.auth.management import create_permissions

from project import settings

from django.apps import apps


def post_migrate_create_organization(sender, **kwargs):
    for app_config in apps.get_app_configs():
        create_permissions(app_config, apps=apps, verbosity=0)

    Organization = sender.get_model('Organization')
    org, created = Organization.objects.get_or_create(name='MIT', url='https://lookit.mit.edu')


def post_migrate_create_social_app(sender, **kwargs):
    Site = apps.get_model('sites.Site')
    SocialApp = apps.get_model('socialaccount.SocialApp')
    site = Site.objects.first()

    site.domain = settings.SITE_DOMAIN
    site.name = settings.SITE_NAME

    site.save()

    if not SocialApp.objects.exists():
        app = SocialApp.objects.create(
            key='',
            name='OSF',
            provider='osf',
            # Defaults are valid for staging
            client_id=os.environ.get('OSF_OAUTH_CLIENT_ID', '3518b74e12584abf9e48565ff6aee6f3'),
            secret=os.environ.get('OSF_OAUTH_SECRET', 'vYlku3raTL5DnHZlkqCIaShmPVIl1nifsFJCNLxU'),
        )
        app.sites.clear()
        app.sites.add(site)


def post_migrate_create_flatpages(sender, **kwargs):
    Site = apps.get_model('sites.Site')
    FlatPage = apps.get_model('flatpages.FlatPage')
    flatpages = [
        dict(url='/', title='Home', content=
        """
        <div class="main">
        	<div class="home-jumbotron">
        		<div class="content">
        			<h1>Lookit<br>
        			<small>the online child lab</small></h1>
        			<p>A project of the MIT Early Childhood Cognition Lab</p><a class="btn btn-primary btn-lg ember-view" href="/studies" id="ember821">Participate in a Study</a>
        		</div>
        	</div>
        	<div class="information-row lookit-row">
        		<div class="container">
        			<div class="row">
        				<div class="col-md-4">
        					<div class="home-content-icon">
        						<i class="fa fa-flask"></i>
        					</div>
        					<h3 class="text-center">Bringing science home</h3>
        					<p>Here at MIT's Early Childhood Cognition Lab, we're trying a new approach in developmental psychology: bringing the experiments to you.</p>
        				</div>
        				<div class="col-md-4">
        					<div class="home-content-icon">
        						<i class="fa fa-cogs"></i>
        					</div>
        					<h3 class="text-center">Help us understand how your child thinks</h3>
        					<p>Our online studies are quick and fun, and let you as a parent contribute to our collective understanding of the fascinating phenomenon of children's learning. In some experiments you'll step into the role of a researcher, asking your child questions or controlling the experiment based on what he or she does.</p>
        				</div>
        				<div class="col-md-4">
        					<div class="home-content-icon">
        						<i class="fa fa-coffee"></i>
        					</div>
        					<h3 class="text-center">Participate whenever and wherever</h3>
        					<p>Log in or create an account at the top right to get started! You can participate in studies from home by doing an online activity with your child that is videotaped via your webcam.</p>
        				</div>
        			</div>
        		</div>
        	</div>
        	<div class="news-row lookit-row">
        		<div class="container">
        			<div class="row">
        				<h3>News</h3>
        				<div class="col-xs-12">
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							March 30, 2017
        						</div>
        						<div class="col-md-7">
        							Our two papers describing online replications of classic developmental studies on a prototype of the Lookit system are now available in the <a href="http://www.mitpressjournals.org/doi/abs/10.1162/OPMI_a_00002#.WN2QeY61vtc">first issue of Open Mind</a>, a new open-access journal from MIT Press! Thank you so much to all of our early participants who made this work possible.
        						</div>
        					</div>
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							September 16, 2016
        						</div>
        						<div class="col-md-7">
        							We're back up and running! If you had an account on the old site, you should have received an email letting you know how to access your new account. We're getting started by piloting a study about babies' intuitive understanding of physics!
        						</div>
        					</div>
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							August 4, 2016
        						</div>
        						<div class="col-md-7">
        							Lookit is taking a break while our partners at the Center for Open Science work on re-engineering the site so it's easier for both parents and researchers to use. We're looking forward to re-opening the login system and starting up some new studies early this fall! Please contact lookit@mit.edu with any questions.
        						</div>
        					</div>
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							October 1, 2015
        						</div>
        						<div class="col-md-7">
        							We've finished collecting data for replications of three classic studies, looking at infants' and children's understanding of probability, language, and reliability. The results will be featured here as soon as they're published!
        						</div>
        					</div>
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							June 30, 2014
        						</div>
        						<div class="col-md-7">
        							An MIT News press release discusses Lookit <a href="https://newsoffice.mit.edu/2014/mit-launches-online-lab-early-childhood-learning-lookit">here</a>. The project was also featured in <a href="http://www.bostonmagazine.com/health/blog/2014/06/19/new-mit-lab/">Boston Magazine</a> and on the <a href="https://www.sciencenews.org/blog/growth-curve/your-baby-can-watch-movies-science">Science News blog</a>. Stay up-to-date and connect with other science-minded parents through our <a href="https://www.facebook.com/lookit.mit.edu">Facebook page</a>!
        						</div>
        					</div>
        					<div class="row">
        						<div class="col-md-2 col-md-offset-1">
        							February 5, 2014
        						</div>
        						<div class="col-md-7">
        							Beta testing of Lookit within the MIT community begins! Many thanks to our first volunteers.
        						</div>
        					</div>
        				</div>
        			</div>
        		</div>
        	</div>
        	<footer>
        		<div class="footer-row lookit-row">
        			<div class="container">
        				<div class="row">
        					<div class="col-md-1"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/nsf.gif"></div>
        					<div class="col-md-11">
        						This material is based upon work supported by the National Science Foundation (NSF) under Grant No. 1429216; the Center for Brains, Minds and Machines (CBMM), funded by NSF STC award CCF-1231216, and by an NSF Graduate Research Fellowship under Grant No. 1122374. Any opinion, findings, and conclusions or recommendations expressed in this material are those of the authors(s) and do not necessarily reflect the views of the National Science Foundation.
        					</div>
        				</div>
        			</div>
        		</div>
        	</footer>
        </div>
        """),
        dict(url='/faq/', title='FAQ', content=
        """
        <div class="main">
        	<div class="lookit-row lookit-page-title">
        		<div class="container">
        			<h2>Frequently Asked Questions</h2>
        		</div>
        	</div>
        	<div class="lookit-row faq-row">
        		<div class="container">
        			<h3>Participation</h3>
        			<div class="panel-group" id="accordion" role="tablist">
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse1">What is a "study" about cognitive development?</a></h4>
        					</div>
        					<div id="collapse1" class="panel-collapse collapse" >
        						<div class="panel-body">
        							<div>
        								<p>Cognitive development is the science of what kids understand and how they learn. Researchers in cognitive development are interested in questions like...</p>
        								<ul>
        									<li>what knowledge and abilities infants are born with, and what they have to learn from experience</li>
        									<li>how abilities like mathematical reasoning are organized and how they develop over time</li>
        									<li>what strategies children use to learn from the wide variety of data they observe</li>
        								</ul>
        								<p>A study is meant to answer a very specific question about how children learn or what they know: for instance, "Do three-month-olds recognize their parents' faces?"</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse2">How can we participate online?</a></h4>
        					</div>
        					<div id="collapse2" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>If you have any children between 3 months and 7 years old and would like to participate, create an account and take a look at what we have available for your child's age range. You'll need a working webcam to participate.</p>
        								<p>When you select a study, you'll be asked to read a consent form and record yourself stating that you and your child agree to participate. Then we'll guide you through what will happen during the study. Depending on your child's age, your child may answer questions directly or we may be looking for indirect signs of what she thinks is going on--like how long she looks at a surprising outcome.</p>
        								<p>Some portions of the study will be automatically recorded using your webcam and sent securely to our MIT lab. Trained researchers will watch the video and record your child's responses--for instance, which way he pointed, or how long she looked at each image. We'll put these together with responses from lots of other children to learn more about how kids think!</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading collapsed" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse3">How do we provide consent to participate?</a></h4>
        					</div>
        					<div id="collapse3" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Rather than having the parent or legal guardian sign a form, we ask that you read aloud (or sign in ASL) a statement of consent which is recorded using your webcam and sent back to our lab. This statement holds the same weight as a signed form, but should be less hassle for you. It also lets us verify that you understand written English and that you understand you're being videotaped.</p>
        								<p>If we receive a consent form that does NOT clearly demonstrate informed consent--for instance, we see a parent and child but the parent does not read the statement--any other video collected during that session will be deleted without viewing.</p>
        								<div class="row">
        									<div class="col-sm-10 col-sm-offset-1 col-md-8 col-md-offset-2 col-lg-6 col-lg-offset-3">
        										<video controls="true" src="https://storage.googleapis.com/io-osf-lookit-staging2/static/videos/consent.mp4"></video>
        									</div>
        								</div>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse4">How is our information kept confidential?</a></h4>
        					</div>
        					<div id="collapse4" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>We do not publish or use identifying information about individual children or families. We never publish children's names or birthdates (birthdates are used only to figure out how old children are at the time of the study). Your video is transmitted over a secure https connection to our lab and kept on a password-protected server. See 'Who will see our video?'</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse5">Who will see our video?</a></h4>
        					</div>
        					<div id="collapse5" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Trained MIT researchers who have been approved to work on the "Lookit" project will watch the video segments you send to mark down information specific to the study--for instance, what your child said, or how long he/she looked to the left versus the right of the screen.</p>
        								<p>Whether anyone else may view the video depends on the privacy settings you select at the end of the study. There are two decisions to make: whether to allow your data to be used by the Lookit team only or to share with Databrary, and how to allow your video clips to be used by the researchers you have selected.</p>
        								<p>First, we ask if you would like to share your data (including video) with authorized users fo the secure data library Databrary. Data sharing will lead to faster progress in research on human development and behavior. Researchers who are granted access to the Databrary library must agree to treat the data with the same high standard of care they would use in their own laboratories. Learn more about Databrary's <a href="https://databrary.org/about/mission.html">mission</a> or the <a href="https://databrary.org/access/responsibilities/investigators.html">requirements for authorized users</a>.</p>
        								<p>Next, we ask what types of uses of your video are okay with you.</p>
        								<ul>
        									<li><strong>Private</strong> This privacy level ensures that your video clips will be viewed only by authorized scientists (researchers working on the Lookit project and, if you have opted to share your data with Databrary, authorized Databrary users.) We will view the videos to record information about what your child did during the study--for instance, looking for 9 seconds at one image and 7 seconds at another image.</li>
        									<li><strong>Scientific and educational</strong> This privacy level gives permission to share your video clips with other researchers or students for scientific or educational purposes. For example, we might show a video clip in a talk at a scientific conference or an undergraduate class about cognitive development, or include an image or video in a scientific paper. In some circumstances, video or images may be available online, for instance as supplemental material in a scientific paper. Sharing videos with other researchers helps other groups trust and build on our work.</li>
        									<li><strong>Publicity</strong> This privacy level is for families who would be excited to see their child featured on the Lookit website or in the news! Selecting this privacy level gives permission to use your video clips to communicate about developmental studies and the Lookit platform with the public. For instance, we might post a short video clip on the Lookit website, on our Facebook page, or in a press release. Your video will never be used for commercial purposes.</li>
        								</ul>
        								<p>If for some reason you do not select a privacy level, we treat the data as 'Private' and do not share with Databrary. Participants also have the option to withdraw all video besides consent at the end of the study if necessary (for instance, because someone was discussing state secrets in the background). Privacy settings for completed sessions cannot be changed retroactively. If you have any questions or concerns about privacy, please contact our team at <a href="mailto:lookit@mit.edu">lookit@mit.edu</a>.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse6">What information does the lab use from our video?</a></h4>
        					</div>
        					<div id="collapse6" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>For children under about two years old, we usually design our studies to let their eyes do the talking! We're interested in where on the screen your child looks and/or how long your child looks at the screen rather than looking away. Our calibration videos (example shown below) help us get an idea of what it looks like when your child is looking to the right or the left, so we can code the rest of the video.</p>
        								<div class="row">
        									<div class="col-sm-10 col-sm-offset-1 col-md-8 col-md-offset-2 col-lg-6 col-lg-offset-3">
        										<video controls="true" src="https://storage.googleapis.com/io-osf-lookit-staging2/static/videos/attentiongrabber.mp4"></video>
        									</div>
        								</div>
        								<p>Here's an example of a few children watching our calibration video--it's easy to see that they look to one side and then the other.</p>
        								<div class="row">
        									<div class="col-sm-10 col-sm-offset-1 col-md-8 col-md-offset-2 col-lg-6 col-lg-offset-3">
        										<video controls="true" src="https://storage.googleapis.com/io-osf-lookit-staging2/static/videos/spinningball.mp4"></video>
        									</div>
        								</div>
        								<p>Your child's decisions about where to look can give us lots of information about what he or she understands. Here are some of the techniques our lab uses to learn more about how children learn.</p>
        								<h4>Habituation</h4>
        								<p>In a habituation study, we first show infants many examples of one type of object or event, and they lose interest over time. Infants typically look for a long time at the first pictures, but then they start to look away more quickly. Once their looking times are much less than they were initially, we show either a picture from a new category or a new picture from the familiar category. If infants now look longer to the novel example, we can tell that they understood--and got bored of--the category we showed initially.</p>
        								<p>Habituation requires waiting for each individual infant to achieve some threshold of "boredness"--for instance, looking half as long at a picture as he or she did initially. Sometimes this is impractical, and we use familiarization instead. In a familiarization study, we show all babies the same number of examples, and then see how interested they are in the familiar versus a new category. Younger infants and those who have seen few examples tend to show a familiarity preference--they look longer at images similar to what they have seen before. Older infants and those who have seen many examples tend to show a novelty preference--they look longer at images that are different from the ones they saw before. You probably notice the same phenomenon when you hear a new song on the radio: initially you don't recognize it; after it's played several times you may like it and sing along; after it's played hundreds of times you would choose to listen to anything else.</p>
        								<h4>Violation of expectation</h4>
        								<p>Infants and children already have rich expectations about how events work. Children (and adults for that matter) tend to look longer at things they find surprising, so in some cases, we can take their looking times as a measure of how surprised they are.</p>
        								<h4>Preferential looking</h4>
        								<p>Even when they seem to be passive observers, children are making lots of decisions about where to look and what to pay attention to. In this technique, we present children with a choice between two side-by-side images or videos, and see if children spend more time looking at one of them. We may additionally play audio that matches one of the videos. The video below shows a participant looking to her left when asked to "find clapping"; the display she's watching is shown at the top.</p>
        								<div class="row">
        									<div class="col-sm-10 col-sm-offset-1 col-md-8 col-md-offset-2 col-lg-6 col-lg-offset-3">
        										<video controls="true" src="https://storage.googleapis.com/io-osf-lookit-staging2/static/videos/clapping.mp4"></video>
        									</div>
        								</div>
        								<h4>Predictive looking</h4>
        								<p>Children can often make sophisticated predictions about what they expect to see or hear next. One way we can see those predictions in young children is to look at their eye movements. For example, if a child sees a ball roll behind a barrier, he may look to the other edge of the barrier, expecting the ball to emerge there. We may also set up artificial predictive relationships--for instance, the syllable "da" means a toy will appear at the left of the screen, and "ba" means a toy will appear at the right. Then we can see whether children learn these relationships, and how they generalize, by watching where they look when they hear a syllable.</p>
        								<p></p>
        								<p>Older children may simply be able to answer spoken questions about what they think is happening. For instance, in the "Learning from Others" study we ran last year, two women call an object two different made-up names, and children are asked which is the correct name for the object.</p>
        								<div class="row">
        									<div class="col-sm-10 col-sm-offset-1 col-md-8 col-md-offset-2 col-lg-6 col-lg-offset-3">
        										<video controls="true" src="https://storage.googleapis.com/io-osf-lookit-staging2/static/videos/causal_ex2.mp4"></video>
        									</div>
        								</div>
        								<p>Another way we can learn about how older children (and adults) think is to measure their reaction times. For instance, we might ask you to help your child learn to press one key when a circle appears and another key when a square appears, and then look at factors that influence how quickly they press a key.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse7">Why are you running studies online?</a></h4>
        					</div>
        					<div id="collapse7" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Traditionally, developmental studies happen in a quiet room in a university lab. Researchers call or email local parents to see if they'd like to take part and schedule an appointment for them to come visit the lab. Why complement these in-lab studies with online ones? We're hoping to...</p>
        								<ul>
        									<li>Make it easier for you to take part in research, especially for families without a stay-at-home parent</li>
        									<li>Work with more kids when needed--right now a limiting factor in designing studies is the time it takes to recruit participants</li>
        									<li>Draw conclusions from a more representative population of families--not just those who live near a university and are able to visit the lab during the day. (To learn more about efforts throughout the scientific community to represent a broader range of subjects, visit <a href="http://lessweird.org/">Making Science Less WEIRD!</a>)
        									</li>
        									<li>Make it easier for families to continue participating in longitudinal studies, which may involve multiple testing sessions separated by months or years</li>
        									<li>Observe more natural behavior because children are at home rather than in an unfamiliar place</li>
        									<li>Create a system for learning about special populations--for instance, children with specific developmental disorders</li>
        									<li>Make the procedures we use in doing research more transparent, and make it easier to replicate our findings</li>
        									<li>Communicate with families about the research we're doing and what we can learn from it</li>
        								</ul>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse8">When will we see the results of the study?</a></h4>
        					</div>
        					<div id="collapse8" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>The process of publishing a scientific study, from starting data collection to seeing the paper in a journal, can take several years. You can check the Lookit home page for updates on papers, or set your communication preferences to be notified when we have results from studies you participated in.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse9">My child wasn't paying attention, or we were interrupted. Can we try the study again?</a></h4>
        					</div>
        					<div id="collapse9" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Certainly--thanks for your dedication! You may see a warning that you have already participated in the study when you go to try it again. You don't need to tell us that you tried the study before; we'll have a record of your previous participation.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse10">My child is outside the age range. Can he/she still participate in this study?</a></h4>
        					</div>
        					<div id="collapse10" class="panel-collapse collapse" >
        						<div class="panel-body">
        							<div>
        								<p>Sure! We may not be able to use his or her data in our research directly, but if you're curious you're welcome to try the study anyway. If your child is just below the minimum age for a study, however, we encourage you to wait so that we'll be able to use the data.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse11">My child was born prematurely. Should we use his/her adjusted age?</a></h4>
        					</div>
        					<div id="collapse11" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>For study eligibility, we usually use the child's chronological age (time since birth), even for premature babies. We ask for the child's gestational age at birth when you register a child so that we can also use the adjusted age in our analysis. If adjusted age is important for a particular study, we will make that clear in the study description.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse12">Our family speaks a language other than English at home. Can my child participate?</a></h4>
        					</div>
        					<div id="collapse12" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Sure! Right now, instructions for children and parents are written only in English, so some of them may be confusing to a child who does not hear English regularly. However, you're welcome to try any of the studies and translate for your child if you can. If it matters for the study whether your child speaks any languages besides English, we'll ask specifically. You can also indicate the languages your child speaks or is learning to speak on your demographic survey.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse13">My child has been diagnosed with a developmental disorder or has special needs. Can he/she still participate?</a></h4>
        					</div>
        					<div id="collapse13" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Of course! We're interested in how all children learn and grow. If you'd like, you can make a note of any developmental disorders in the comments section at the end of the study. Any health information provided will be kept confidential. We are excited that in the future, online studies may help more families participate in research to better understand their own children's diagnoses.</p>
        								<p>One note: most of our studies include both images and sound, and may be hard to understand if your child is blind or deaf. If you can, please feel free to help out by describing images or signing.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading collapsed" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse14">I have multiple children in the age range for a study. Can they participate together?</a></h4>
        					</div>
        					<div id="collapse14" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>If possible, we ask that each child participate separately. When children participate together they generally influence each other. That's a fascinating subject in its own right but usually not the focus of our research.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse15">I've heard that young children should avoid "screen time."</a></h4>
        					</div>
        					<div id="collapse15" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>We agree with the American Academy of Pediatrics <a href="https://pediatrics.aappublications.org/content/138/5/e20162591" target="_blank">advice</a> that children learn best from people, not screens! However, our studies are not intended to educate children, but to learn from them.</p>
        								<p>As part of a child's limited screen time, we hope that our studies will foster family conversation and engagement with science that offsets the few minutes spent watching a video instead of playing. And we do "walk the walk"--our own young children (okay, mostly Kim's son Remy) provide lots of feedback on our studies before we make them available to you!</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse16">Will we be paid for our participation?</a></h4>
        					</div>
        					<div id="collapse16" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>In general, no, there are no direct benefits from participating in our studies. We hope they are interesting for both you and your child!</p>
        								<p>Sometimes we do post studies as tasks on Amazon Mechanical Turk so that we can reimburse families for participation. You can check our current listings <a href="https://www.mturk.com/mturk/searchbar?selectedSearchType=hitgroups&amp;requesterId=A2UX8MLL4VGZM7">here</a>.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading collapsed" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse17">Can I get my child's results?</a></h4>
        					</div>
        					<div id="collapse17" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>For some studies, yes! Usually, we only interpret children's abilities and developmental trends at a group level, so the individual data collected just isn't very interpretable. But for "Baby physics" and other longitudinal studies (where we ask you to come back for more than one session), we'll be collecting enough data to give you a report of your child's responses after you complete all the sessions. Because this is a fairly labor-intensive process (we generally have two undergraduates watch each video and record where your child is looking each frame, and then we do some analysis to create a summary), it may take us several weeks to produce your report.</p>
        								<p>Please note that none of the measures we collect are diagnostic! For instance, while we hope you'll be interested to learn that your child looked 70% of the time at videos where things fell up versus falling down, we won't be able to tell you whether this means your child is going to be especially good at physics.</p>
        								<p>We are generally able to provide general feedback (confirming that we got your video and will be able to use it) within a week. To see this feedback, log in, then go to "Studies" and select "Past Studies."</p>
        								<p>If you're interested in getting individual results right away, please see our <a href="/resources">Resources</a> section for fun at-home activities you can try with your child.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        			</div>
        			<h3>Technical</h3>
        			<div class="panel-group" role="tablist">
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse18">What browsers are supported?</a></h4>
        					</div>
        					<div id="collapse18" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Lookit supports recent versions of Chrome, Firefox, and Safari. We are not currently able to support Internet Explorer.</p>
        							</div>
        						</div>
        					</div>
        				</div>
        				<div class="panel panel-default">
        					<div class="panel-heading" role="tab">
        						<h4 class="panel-title"><a data-toggle="collapse" data-parent="#accordion" href="#collapse19">Can we do a study on my phone or tablet?</a></h4>
        					</div>
        					<div id="collapse19" class="panel-collapse collapse">
        						<div class="panel-body">
        							<div>
        								<p>Not yet! Because we're measuring kids' looking patterns, we need a reasonably stable view of their eyes and a big enough screen that we can tell whether they're looking at the left or the right side of it. We're excited about the potential for touchscreen studies that allow us to observe infants and toddlers exploring, though!</p>
        							</div>
        						</div>
        					</div>
        				</div>
        			</div>
        		</div>
        	</div>
        </div>
        """),
        dict(url='/scientists/', title='The Scientists', content=
        """
        <div class="main">
        	<div class="lookit-row lookit-page-title">
        		<div class="container">
        			<h2>Meet the Scientists</h2>
        		</div>
        	</div>
        	<div class="lookit-row scientists-row">
        		<div class="container">
        			<div class="row">
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/kimandremy.png"></div>
        					<h3>Kim Scott</h3>
        					<p>Kim is a graduate student in the Early Childhood Cognition Lab and Mama to six-year-old Remy. She developed Lookit partly to enable other single parents to participate in research!</p>
        					<p>Research interests: Origins of conscious experience--or what it's like to be a baby</p>
        					<p>Hobbies: Board games, aerial silks, bicycling</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/laura.jpg"></div>
        					<h3>Laura Schulz</h3>
        					<p>Laura is the PI of the Early Childhood Cognition Lab.</p>
        					<p>Research interests: How children arrive at a common-sense understanding of the physical and social world through exploration and instruction.</p>
        					<p>Hobbies: hiking, reading, and playing</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/molly.jpg"></div>
        					<h3>Molly Dillon</h3>
        					<p>Molly is a graduate student in the Lab for Developmental Studies at Harvard. She’ll be starting her own lab in July 2017 as an Assistant Professor at NYU. Molly explores the origins of abstract thought, especially in the domains of geometry and number.</p>
        					<p>Hobbies: ballet, tennis, speaking French</p>
        				</div>
        			</div>
        			<div class="row">
        				<h3>Alumni &amp; Collaborators</h3>
        				<hr>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/jessica.jpg"></div>
        					<h3>Jessica Zhu</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Hobbies: Playing cards, eating watermelon, and hanging out with friends</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/audrey.jpg"></div>
        					<h3>Audrey Ricks (Summer 2016)</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Hobbies: Biking, learning and exploring</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/hope.jpg"></div>
        					<h3>Hope Fuller-Becker (Sp 2015, Sp 2016)</h3>
        					<p>Undergraduate, Wellesley College</p>
        					<p>Hobbies: drawing, painting, reading and running</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/rianna.jpg"></div>
        					<h3>Rianna Shah (IAP, Sp, Fall 2015; IAP, Sp 2016)</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Hobbies: Singing, playing the piano, and karate!</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/junyi.jpg"></div>
        					<h3>Junyi Chu (Summer 2015)</h3>
        					<p>Recent graduate, Vanderbilt University</p>
        					<p>Hobbies: Rock climbing, board and card games</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/joseph.jpg"></div>
        					<h3>Joseph Alvarez (Summer 2015)</h3>
        					<p>Undergraduate, Skidmore College</p>
        					<p>Hobbies: Creating, discovering, and playing electric guitar!</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/annie.jpg"></div>
        					<h3>Annie Dai (IAP, Sp 2015)</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Hobbies: Running, spending time outdoors, listening to music</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/jeanyu.jpg"></div>
        					<h3>Jean Yu (IAP, Sp 2015)</h3>
        					<p>Undergraduate, Wellesley College</p>
        					<p>Hobbies: ballet, figure skating, piano, making art, learning about art, reading about art, learning about the brain</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/daniela.jpg"></div>
        					<h3>Daniela Carrasco (Sp 2015)</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Hobbies: Crossfit athlete, swimming, boxing, painting and sketching</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/jean.jpg"></div>
        					<h3>Jean Chow (Fa 2014)</h3>
        					<p>Undergraduate, MIT</p>
        					<p>Research interests: cognitive development and learning in young children</p>
        					<p>Hobbies: Running, cycling, Taekwondo, art, being outdoors, chilling with her dog</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/melissa.png"></div>
        					<h3>Melissa Kline</h3>
        					<p>As a graduate student in the Early Childhood Cognition Lab, Melissa advised and designed stimuli for the "Learning New Verbs" study.</p>
        					<p>Hobbies: Sewing, tango, and singing.</p>
        				</div>
        				<div class="lookit-scientist col-sm-6 col-md-4 col-lg-3">
        					<div class="profile-img"><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/rachel.png"></div>
        					<h3>Rachel Magid</h3>
        					<p>Rachel is now a graduate student at ECCL; in her two years as our lab coordinator she helped get Lookit off the ground!</p>
        					<p>Hobbies: Reading historical fiction and cooking</p>
        				</div>
        			</div>
        		</div>
        	</div>
        </div>
        """),
        dict(url='/resources/', title='Resources', content=
        """
        <div class="main">
        	<div class="lookit-row lookit-page-title">
        		<div class="container">
        			<h2>Resources</h2>
        		</div>
        	</div>
        	<div class="lookit-row resources-row">
        		<div class="container">
        			<div class="resources-item">
        				<h3>Find a developmental lab near you</h3>
        				<p>Interested in participating in research in person? Find a list of labs that study child development in your state.</p>
        				<p>Did we miss your lab, or one you know about? Our apologies, and please let us know at <a href="mailto:lookit-ed@mit.edu">lookit-ed@mit.edu</a></p>
        				<div>
        					<div class="row resources-local">
        						<div class="col-md-4">
                                    <select id="state-select" onchange="populateLabList(this.value)">
                                        <option></option>
                                        <option>Alabama</option>
                                        <option>Alaska</option>
                                        <option>Arizona</option>
                                        <option>Arkansas</option>
                                        <option>California</option>
                                        <option>Colorado</option>
                                        <option>Connecticut</option>
                                        <option>Delaware</option>
                                        <option>Florida</option>
                                        <option>Georgia</option>
                                        <option>Hawaii</option>
                                        <option>Idaho</option>
                                        <option>Illinois</option>
                                        <option>Indiana</option>
                                        <option>Iowa</option>
                                        <option>Kansas</option>
                                        <option>Kentucky</option>
                                        <option>Louisiana</option>
                                        <option>Maine</option>
                                        <option>Maryland</option>
                                        <option>Massachusetts</option>
                                        <option>Michigan</option>
                                        <option>Minnesota</option>
                                        <option>Mississippi</option>
                                        <option>Missouri</option>
                                        <option>Montana</option>
                                        <option>Nebraska</option>
                                        <option>Nevada</option>
                                        <option>New Hampshire</option>
                                        <option>New Jersey</option>
                                        <option>New Mexico</option>
                                        <option>New York</option>
                                        <option>North Carolina</option>
                                        <option>North Dakota</option>
                                        <option>Ohio</option>
                                        <option>Oklahoma</option>
                                        <option>Oregon</option>
                                        <option>Pennsylvania</option>
                                        <option>Rhode Island</option>
                                        <option>South Carolina</option>
                                        <option>South Dakota</option>
                                        <option>Tennessee</option>
                                        <option>Texas</option>
                                        <option>Utah</option>
                                        <option>Vermont</option>
                                        <option>Virginia</option>
                                        <option>Washington</option>
                                        <option>West Virginia</option>
                                        <option>Wisconsin</option>
                                        <option>Wyoming</option>
                                    </select>
        						</div>
        						<div class="col-md-8">
        							<b class='selected-state'></b>
                                    <p id="nothing-to-show"></p>
        							<ul id="lab-list">
        							</ul>
        						</div>
        					</div>
        				</div>
        			</div>
        			<hr>
        			<div class="resources-item">
        				<h3>Looking for other 'citizen science' projects your family can help?</h3>
        				<p>Check out <a href="http://scistarter.com/index.html">SciStarter</a>, which has many projects suitable for elementary school age children and up, and for the whole family to explore together!</p>
        			</div>
        			<hr>
        			<div class="resources-item">
        				<h3>Activities to try at home</h3>
        				<p>Want to learn more about cognitive development? Here are some activities that may give you some insight into your own child's developing mind. Instead of studies our lab is running, these are "at home labs" for parents to try on their own--but please feel free to contact us with any questions!</p>
        				<h4>Learning about other minds: your child's developing theory of mind</h4><iframe allowfullscreen frameborder="0" height="315" src="https://www.youtube.com/embed/uxyVYATX9-M" width="560"></iframe>
        				<p><strong>Age range</strong>: 2.5 to 5 years</p>
        				<p><strong>What you'll need</strong>: For the "Maxi and the chocolate" story, any props you'd like (you can try drawing a picture or acting out the story). For the word-learning task, two containers to hold two objects your child doesn't know a name for (weird household objects like whisks or bike parts work great).</p>
        				<p>In this lab, you'll see how your child thinks about what other people are thinking. Children under about four years of age tend to show a lot of trouble expressing what's going on in situations where someone else knows less than they do. They will often absolutely insist that everyone knows what they themselves know!</p>
        				<h4>Learning to count: measuring your child's N-knower level</h4><iframe allowfullscreen frameborder="0" height="315" src="https://www.youtube.com/embed/i0q6H8MRXo8" width="560"></iframe>
        				<p><strong>Age range</strong>: 1 to 5 years</p>
        				<p><strong>What you'll need</strong>: At least ten small objects your child can pick up, like pegs or Cheerios</p>
        				<p><strong>A guided, online "give N" task is coming soon to Lookit!</strong></p>
        				<h4>Let your baby choose: understanding your infant's preferences</h4>
        				<p><img src="https://storage.googleapis.com/io-osf-lookit-staging2/static/images/pacifier.png"></p>
        				<p><strong>Age range</strong>: 0 to 6 months</p>
        				<p><strong>What you'll need</strong>: A pacifier that your infant will suck on for about 15 minutes at a time and the operant conditioning web tool.</p>
        				<p>In this lab, you'll let your baby control what sound is played by sucking faster or slower on a pacifier. We recommend starting by trying to observe his or her preference for hearing music or a heartbeat. <a href="http://www.mit.edu/~kimscott/instructions.html">Instructions</a></p>
        			</div>
        		</div>
        	</div>
        </div>
        <script type="text/javascript">
            var allLabs = {
                "Alabama": [
                    {
                        'url': 'http://www.ches.ua.edu/hdfs/cdrc/',
                        'name': 'University of Alabama Child Development Research Center'
                    },
                    {
                        'url': 'http://monaelsheikh.com/',
                        'name': 'Auburn University Child Sleep, Health, and Development Lab'
                    }
                ],
                "Alaska": [],
                "Arizona": [
                    {
                        'url': 'http://web.arizona.edu/~tigger/',
                        'name': 'University of Arizona Child Cognition Lab (Tigger Lab)'
                    },
                    {
                        'url': 'http://web.arizona.edu/~tweety/',
                        'name': 'University of Arizona Language Development Lab (Tweety Lab)'
                    },
                    {
                        'url': 'http://nau.edu/SBS/IHD/Research/CDLL/',
                        'name': 'Northern Arizona University Child Development and Language Lab'
                    }
                ],
                "Arkansas": [
                    {
                        'url': 'http://acnc.uamsweb.com/research-2/our-laboratories-2/early-diets-and-long-term-health-lab/',
                        'name': "Arkansas Children's Nutrition Center Growth and Development Laboratory"
                    }
                ],
                "California": [
                    {
                        'url': 'http://www.csus.edu/indiv/a/alexanderk/lab.htm',
                        'name': 'CSU Sacramento Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www-psych.stanford.edu/~babylab/',
                        'name': "Stanford's Center for Infant Studies"
                    },
                    {
                        'url': 'http://bungelab.berkeley.edu/participate/',
                        'name': 'UC Berkeley Building Blocks of Cognition Lab'
                    },
                    {
                        'url': 'http://babycenter.berkeley.edu/',
                        'name': 'UC Berkeley Infant Studies Center'
                    },
                    {
                        'url': 'http://psychology.berkeley.edu/participant-recruitment/rsvp-research-subject-volunteer-pool',
                        'name': 'UC Berkeley Psychology Department (list of studies)'
                    },
                    {
                        'url': 'http://oakeslab.ucdavis.edu/',
                        'name': 'UC Davis Infant Cognition Lab'
                    },
                    {
                        'url': ' http://languagelearninglab.dss.ucdavis.edu/',
                        'name': 'UC Davis Language Learning Lab'
                    },
                    {
                        'url': ' http://riveralab.ucdavis.edu/',
                        'name': 'UC Davis Neurocognitive Development Lab'
                    },
                    {
                        'url': 'http://www.cogsci.uci.edu/cogdev/information.html',
                        'name': 'UC Irvine Sarnecka Cognitive Development Lab'
                    },
                    {
                        'url': 'http://babytalk.psych.ucla.edu/home.htm',
                        'name': 'UCLA Language and Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.ccl.ucr.edu/',
                        'name': 'UC Riverside Childhood Cognition Lab'
                    },
                    {
                        'url': 'https://labs.psych.ucsb.edu/german/tamsin/',
                        'name': 'UCSB Cognition & Development Laboratory'
                    },
                    {
                        'url': 'http://www-cogsci.ucsd.edu/~deak/cdlab/',
                        'name': 'UCSD Cognitive Development Lab'
                    },
                    {
                        'url': 'http://dornsife.usc.edu/labs/mid-la/participate/',
                        'name': 'USC Minds in Development Lab'
                    }
                ],
                "Colorado": [
                    {
                        'url': 'http://sleep.colorado.edu/',
                        'name': 'UC Boulder Sleep and Development Lab'
                    },
                    {
                        'url': 'http://www.ucdenver.edu/academics/colleges/medicalschool/departments/psychiatry/Research/developmentalresearch/Pages/Overview.aspx',
                        'name': 'University of Colorado Denver Developmental Psychiatry Research Group'
                    },
                    {
                        'url': 'http://www.du.edu/psychology/child_health_and_development/',
                        'name': 'University of Colorado Denver Child Health & Development Lab'
                    },
                    {
                        'url': 'http://psych.colorado.edu/~cdc/whoweare.htm',
                        'name': 'University of Colorado Denver Cognitive Development Center'
                    }
                ],
                "Connecticut": [
                    {
                        'url': 'http://cogdev.research.wesleyan.edu/',
                        'name': 'Wesleyan University Cognitive Development Labs'
                    },
                    {
                        'url': 'http://infantandchild.yale.edu/',
                        'name': 'Yale Infant and Child Research'
                    },
                    {
                        'url': 'http://candlab.yale.edu/',
                        'name': 'Yale Clinical Affective Neuroscience & Development Lab'
                    },
                    {
                        'url': 'https://medicine.yale.edu/lab/mcpartland/',
                        'name': 'McPartland Lab at Yale - Clinical Neuroscience of Autism Spectrum Disorder'
                    }
                ],
                "Delaware": [
                    {
                        'url': 'http://www.childsplay.udel.edu/',
                        'name': "University of Delaware Child's Play, Learning and Development Lab"
                    }
                ],
                "Florida": [
                    {
                        'url': 'http://casgroup.fiu.edu/dcn/pages.php?id=3636',
                        'name': 'FIU Developmental Cognitive Neuroscience Lab'
                    },
                    {
                        'url': 'http://online.sfsu.edu/devpsych/fair/index.html',
                        'name': 'FSU Family Interaction Research Lab'
                    },
                    {
                        'url': 'http://psy2.fau.edu/~lewkowicz/cdlfau/default.htm',
                        'name': 'FAU Child Development Lab'
                    },
                    {
                        'url': 'http://infantlab.fiu.edu/Infant_Lab.htm',
                        'name': 'FIU Infant Development Lab'
                    }
                ],
                "Georgia": [
                    {
                        'url': 'http://www.gcsu.edu/psychology/currentresearch.htm#Participate',
                        'name': 'Georgia College Psychology Department'
                    }
                ],
                "Hawaii": [
                    {
                        'url': 'http://www.psychology.hawaii.edu/concentrations/developmental-psychology.html',
                        'name': 'University of Hawaii Developmental Psychology'
                    }
                ],
                "Idaho": [],
                "Illinois": [
                    {
                        'url': 'http://internal.psychology.illinois.edu/~acimpian/',
                        'name': 'University of Illinois Cognitive Development Lab'
                    },
                    {
                        'url': 'http://internal.psychology.illinois.edu/infantlab/',
                        'name': 'University of Illinois Infant Cognition Lab'
                    },
                    {
                        'url': 'http://bradfordpillow.weebly.com/cognitive-development-lab.html',
                        'name': 'Northern Illinois University Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.childdevelopment.northwestern.edu/',
                        'name': "Northwestern University's Project on Child Development"
                    },
                    {
                        'url': 'http://woodwardlab.uchicago.edu/Home.html',
                        'name': 'University of Chicago Infant Learning and Development Lab'
                    }
                ],
                "Indiana": [
                    {
                        'url': 'http://www.iub.edu/~cogdev/',
                        'name': 'Indiana University Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.psych.iupui.edu/Users/kjohnson/cogdevlab/INDEX.HTM',
                        'name': 'IUPUI Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.evansville.edu/majors/cognitivescience/language.cfm',
                        'name': 'University of Evansville Language and Cognitive Development Laboratory'
                    }
                ],
                "Iowa": [
                    {
                        'url': 'http://www.medicine.uiowa.edu/psychiatry/cognitivebraindevelopmentlaboratory/',
                        'name': 'University of Iowa Cognitive Brain Development Laboratory'
                    }
                ],
                "Kansas": [
                    {
                        'url': 'http://www2.ku.edu/~lsi/labs/neurocognitive_lab/staff.shtml',
                        'name': 'KU Neurocognitive Development of Autism Research Laboratory'
                    },
                    {
                        'url': 'http://healthprofessions.kumc.edu/school/research/carlson/index.html',
                        'name': 'KU Maternal and Child Nutrition and Development Laboratory'
                    },
                    {
                        'url': 'http://greenhoot.wordpress.com/meet-the-research-team/',
                        'name': 'KU Memory and Development Lab'
                    }
                ],
                "Minnesota": [
                    {
                        'url': 'http://www.cehd.umn.edu/icd/research/seralab/',
                        'name': 'University of Minnesota Language and Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.cehd.umn.edu/icd/research/cdnlab/',
                        'name': 'University of Minnesota Cognitive Development & Neuroimaging Lab'
                    },
                    {
                        'url': 'http://www.cehd.umn.edu/icd/research/carlson/',
                        'name': 'University of Minnesota Carlson Child Development Lab'
                    }
                ],
                "Kentucky": [
                    {
                        'url': 'http://babythinker.org',
                        'name': 'University of Louisville Infant Cognition Lab'
                    },
                    {
                        'url': 'http://www.wku.edu/psychological-sciences/labs/cognitive_development/index.php',
                        'name': 'Western Kentucky University Cognitive Development Lab'
                    }
                ],
                "Louisana": [],
                "Maine": [
                    {
                        'url': 'http://people.usm.maine.edu/bthompso/Site/Development%20Lab.html',
                        'name': 'USM Human Development Lab'
                    },
                    {
                        'url': 'http://www.colby.edu/psychology/labs/cogdev1/LabAlumni.html',
                        'name': 'Colby Cognitive Development Lab'
                    }
                ],
                "Maryland": [
                    {
                        'url': 'http://education.umd.edu/HDQM/labs/Fox/',
                        'name': 'University of Maryland Child Development Lab'
                    },
                    {
                        'url': 'http://ncdl.umd.edu/',
                        'name': 'University of Maryland Neurocognitive Development Lab'
                    }
                ],
                "Massachusetts": [
                    {
                        'url': 'http://eccl.mit.edu/',
                        'name': 'MIT Early Childhood Cognition Lab'
                    },
                    {
                        'url': 'http://gablab.mit.edu/',
                        'name': 'MIT Gabrieli Lab'
                    },
                    {
                        'url': 'http://saxelab.mit.edu/people.php',
                        'name': 'MIT Saxelab Social Cognitive Neuroscience Lab'
                    },
                    {
                        'url': 'https://software.rc.fas.harvard.edu/lds/',
                        'name': 'Harvard Laboratory for Developmental Sciences'
                    },
                    {
                        'url': 'http://www.bu.edu/cdl/',
                        'name': 'Boston University Child Development Labs'
                    },
                    {
                        'url': 'babies.umb.edu',
                        'name': 'UMass Boston Baby Lab'
                    },
                    {
                        'url': 'http://people.umass.edu/lscott/lab.htm',
                        'name': 'UMass Amherst Brain, Cognition, and Development Lab'
                    },
                    {
                        'url': 'http://www.northeastern.edu/berentlab/research/infant/',
                        'name': 'Northeastern Infant Phonology Lab'
                    }
                ],
                "Michigan": [
                    {
                        'url': 'http://www.educ.msu.edu/content/default.asp?contentID=903',
                        'name': 'MSU Cognitive Development Lab'
                    },
                    {
                        'url': 'http://ofenlab.wayne.edu/people.php',
                        'name': 'Wayne State University Cognitive Brain Development Lab'
                    }
                ],
                "Mississippi": [],
                "Missouri": [
                    {
                        'url': 'http://www.artsci.wustl.edu/~children/',
                        'name': 'Washington University Cognition and Development Lab'
                    },
                    {
                        'url': 'http://mumathstudy.missouri.edu/#content',
                        'name': 'University of Missouri-Columbia Math Study'
                    }
                ],
                "Montana": [
                    {
                        'url': 'http://hs.umt.edu/psychology/severson/',
                        'name': 'The Minds Lab at University of Montana '
                    },
                    {
                        'url': 'http://www.montana.edu/wwwpy/brooker/html/meet.html',
                        'name': 'Montana State University DOME Lab'
                    }
                ],
                "Nebraska": [
                    {
                        'url': 'http://www.boystownhospital.org/research/clinicalbehavioralstudies/Pages/LanguageDevelopmentLaboratory.aspx',
                        'name': 'Boys Town National Research Hospital Language Development Laboratory'
                    },
                    {
                        'url': 'http://research.unl.edu/dcn/',
                        'name': 'University of Nebraska-Lincoln Developmental Cognitive Neuroscience Laboratory'
                    }
                ],
                "Nevada": [
                    {
                        'url': 'http://www.unl.edu/dbrainlab/',
                        'name': 'University of Nebraska-Lincoln Developmental Brain Lab'
                    }
                ],
                "New Hampshire": [
                    {
                        'url': 'http://cola.unh.edu/news/frl',
                        'name': 'University of New Hampshire Family Research Lab'
                    }
                ],
                "New Jersey": [
                    {
                        'url': 'http://www.shu.edu/academics/gradmeded/ms-speech-language-pathology/dlc-lab.cfm',
                        'name': 'Seton Hall University  Developmental Language and Cognition Laboratory'
                    },
                    {
                        'url': 'http://www.ramapo.edu/sshs/childlab/',
                        'name': 'Ramapo College Child Development Lab'
                    },
                    {
                        'url': 'http://ruccs.rutgers.edu/~aleslie/',
                        'name': 'Rutgers University Cognitive Development Lab'
                    },
                    {
                        'url': 'http://babylab.rutgers.edu/HOME.html',
                        'name': 'Rutgers University Infancy Studies Lab'
                    },
                    {
                        'url': 'http://ruccs.rutgers.edu/languagestudies/people.html',
                        'name': 'Rutgers University Lab for Developmental Language Studies'
                    }
                ],
                "New Mexico": [],
                "New York": [
                    {
                        'url': 'http://www.columbia.edu/cu/needlab/',
                        'name': 'Columbia Neurocognition, Early Experience, and Development (NEED) Lab'
                    },
                    {
                        'url': 'https://www.facebook.com/pages/Child-Development-Lab-the-City-University-of-New-York/42978619994',
                        'name': 'CUNY Child Development Lab'
                    }
                ],
                "North Carolina": [
                    {
                        'url': 'http://people.uncw.edu/nguyens/',
                        'name': 'UNCW Cognitive Development Lab'
                    }
                ],
                "North Dakota": [
                    {
                        'url': 'http://www.cvcn.psych.ndsu.nodak.edu/labs/woods/',
                        'name': 'NDSU Infant Cognitive Development Lab'
                    }
                ],
                "Ohio": [
                    {
                        'url': 'http://cogdev.cog.ohio-state.edu/',
                        'name': 'OSU Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.ohio.edu/chsp/rcs/csd/research/dplab.cfm',
                        'name': 'Ohio University Developmental Psycholinguistics Lab'
                    }
                ],
                "Oklahoma": [],
                "Oregon": [
                    {
                        'url': 'http://bdl.uoregon.edu/Participants/participants.php',
                        'name': 'University of Oregon Brain Development Lab'
                    },
                    {
                        'url': 'http://www.uolearninglab.com',
                        'name': 'University of Oregon Learning Lab'
                    }
                ],
                "Pennsylvania": [
                    {
                        'url': 'http://www.temple.edu/infantlab/',
                        'name': 'Temple Infant & Child Lab'
                    },
                    {
                        'url': 'http://lncd.pitt.edu/wp/',
                        'name': 'University of Pittsburgh Laboratory of Neurocognitive Development'
                    },
                    {
                        'url': 'https://sites.sas.upenn.edu/cogdevlab/',
                        'name': 'UPenn Cognition & Development Lab'
                    },
                    {
                        'url': 'http://babylab.psych.psu.edu/',
                        'name': 'Penn State Brain Development Lab'
                    }
                ],
                "Rhode Island": [
                    {
                        'url': 'http://www.brown.edu/Research/dcnl/',
                        'name': 'Brown University Developmental Cognitive Neuroscience Lab'
                    }
                ],
                "South Carolina": [
                    {
                        'url': 'http://academicdepartments.musc.edu/joseph_lab/',
                        'name': 'MUSC Brain, Cognition, & Development Lab'
                    }
                ],
                "South Dakota": [],
                "Tennessee": [
                    {
                        'url': 'http://web.utk.edu/~infntlab/',
                        'name': 'UT Knoxville Infant Perception-Action Lab'
                    },
                    {
                        'url': 'http://peabody.vanderbilt.edu/departments/psych/research/research_labs/educational_cognitive_neuroscience_lab/index.php',
                        'name': 'Vanderbilt Educational Cognitive Neuroscience Lab'
                    }
                ],
                "Texas": [
                    {
                        'url': 'http://www.ccdlab.net/',
                        'name': 'UT-Austin Culture, Cognition, & Development Lab'
                    },
                    {
                        'url': 'http://homepage.psy.utexas.edu/HomePage/Group/EcholsLAB/',
                        'name': 'UT-Austin Language Development Lab'
                    },
                    {
                        'url': 'http://www.utexas.edu/cola/depts/psychology/areas-of-study/developmental/Labs--Affiliations/CRL.php',
                        'name': "UT-Austin Children's Research Lab"
                    },
                    {
                        'url': 'http://www.uh.edu/class/psychology/dev-psych/research/cognitive-development/index.php',
                        'name': 'University of Houston Cognitive Development Lab'
                    }
                ],
                "Utah": [],
                "Vermont": [
                    {
                        'url': 'http://www.uvm.edu/psychology/?Page=developmental_labs.html&SM=researchsubmenu.html',
                        'name': 'University of Vermont Developmental Laboratories (overview)'
                    }
                ],
                "Virginia": [
                    {
                        'url': 'http://people.jmu.edu/vargakx/',
                        'name': 'James Madison University Cognitive Development Lab'
                    },
                    {
                        'url': 'http://www.psyc.vt.edu/labs/socialdev',
                        'name': 'Virginia Tech Social Development Lab'
                    },
                    {
                        'url': 'http://faculty.virginia.edu/childlearninglab/',
                        'name': 'University of Virginia Child Language and Learning Lab'
                    },
                    {
                        'url': 'http://denhamlab.gmu.edu/labmembers.html',
                        'name': 'George Mason University Child Development Lab'
                    }
                ],
                "Washington": [
                    {
                        'url': 'http://depts.washington.edu/eccl/',
                        'name': 'University of Washington Early Childhood Cognition'
                    },
                    {
                        'url': 'https://depts.washington.edu/uwkids/',
                        'name': 'University of Washington Social Cognitive Development Lab'
                    },
                    {
                        'url': 'http://ilabs.uw.edu/institute-faculty/bio/i-labs-andrew-n-meltzoff-phd',
                        'name': 'University of Washington Infant and Child Studies Lab'
                    }
                ],
                "West Virginia": [
                    {
                        'url': 'http://www.wvuadolescentlab.com/',
                        'name': 'WVU Adolescent Development Lab'
                    }
                ],
                "Wisconsin": [
                    {
                        'url': 'https://sites.google.com/site/haleyvlach/',
                        'name': 'University of Wisconsin Learning, Cognition, & Development Lab'
                    }
                ],
                "Wyoming": []
            };
            $(document).ready(function() {
                $("#state-select").select2({
                    placeholder: "Choose a state",
                    width: '100%',
                });
                $("#state-select")
                    .change(function () {
                        var state = "";
                        $("select option:selected").each(function() {
                            state += $(this).text() + " ";
                        });
                    $(".selected-state").text(state);
                  }).change();
            });
            function populateLabList(state) {
                if (!state) {
                    return;
                }
                var list = document.getElementById('lab-list');
                var nothingToShow = document.getElementById("nothing-to-show");
                nothingToShow.innerHTML="";
                while (list.firstChild) {
                    list.removeChild(list.firstChild);
                }
                var labList = allLabs[state];
                if (labList && labList.length) {
                    for (i = 0; i < labList.length; i++) {
                        var entry = document.createElement('li');
                        var a = document.createElement('a');
                        a.appendChild(document.createTextNode(labList[i].name));
                        a.title = labList[i].name;
                        a.href = labList[i].url;
                        entry.appendChild(a);
                        list.appendChild(entry);
                    }
                } else {
                    nothingToShow.innerHTML = "Sorry, we don't know of any child development labs in " + state + " yet!";
                }
            }
        </script>
        """),
        dict(url='/contact_us/', title='Contact Us', content=
        """
        <div class="main">
        	<div class="lookit-row lookit-page-title">
        		<div class="container">
        			<h2>Contact</h2>
        		</div>
        	</div>
        	<div class="lookit-row contact-row">
        		<div class="container">
        			<h3>Technical difficulties</h3>
        			<p>To report any technical difficulties during participation, please contact our team by email at <a href="mailto:lookit-tech@mit.edu">lookit-tech@mit.edu</a>.</p>
        			<h3>Questions about the studies</h3>
        			<p>If you have any questions or concerns about the studies, please first check our FAQ. With any additional questions, please contact us at <a href="mailto:lookit@mit.edu">lookit@mit.edu</a>.</p>
        			<h3>For researchers</h3>
        			<p>We are committed to making Lookit a tool for all developmental researchers and to keeping the code open-source. You can view the current <a href="https://github.com/CenterForOpenScience/lookit" target="_blank">Lookit</a>, <a href="https://github.com/CenterForOpenScience/experimenter" target="_blank">Experimenter</a>, and <a href="https://github.com/CenterForOpenScience/exp-addons" target="_blank">exp-addons</a> (specific frames for Lookit studies) codebases on github; <a href="https://github.com/kimberscott?tab=repositories" target="_blank">Kim's forks</a> may have more up-to-date versions of data analysis code.</p>
        			<p>We're not quite ready to start hosting additional studies from other labs yet, but our partners at the Center for Open Science are actively developing functionality for multiple labs to create and post their own studies on Lookit. Although we aim for the platform to be as accessible as possible, some familiarity with programming basics will be helpful for researchers. An ideal skillset for creating your own studies would include basic understanding of HTML, CSS, and JavaScript for study creation; passing familiarity with the <a href="https://guides.emberjs.com/v2.8.0/" target="_blank">Ember framework</a> used by Lookit and Experimenter; and python for data processing.</p>
        			<p>For updates on the Lookit platform and discussions about collaboration opportunities, you can <a href="http://mailman.mit.edu/mailman/listinfo/lookit-research" target="_blank">join the lookit-research email list</a>. Several initial test studies of a prototype Lookit platform were completed in 2015; please email Kim Scott (kimscott@mit.edu) if you'd like in-press manuscripts describing the results.</p>
        		</div>
        	</div>
        </div>
        """),
    ]
    site = Site.objects.first()

    site.domain = settings.SITE_DOMAIN
    site.name = settings.SITE_NAME

    site.save()

    for page in flatpages:
        defaults = dict(content=page.pop('content'))
        flatpage_obj, created = FlatPage.objects.get_or_create(defaults=defaults, **page)
        flatpage_obj.sites.add(site)
