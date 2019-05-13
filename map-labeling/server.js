const Express = require('express');
const Mustache = require('mustache');
const MustacheExpress = require('mustache-express');
const Path = require('path');
const Mongoose = require('mongoose');
const _ = require('lodash');
const BodyParser = require("body-parser");

const tiles = require('./tiles.json');

const MapLabelOverlay = Mongoose.model('MapLabelOverlay', {
  tile: String,
  authorName: String,
  authorEmail: String,
  authorIpAddress: String,
  timestamp: Date,
  image: String,
});

const app = Express();

app.use(BodyParser.json({ limit: '1mb' }));
app.disable("x-powered-by");

app.engine('html', MustacheExpress());
app.set('view engine', 'html');
app.set('views', __dirname);

app.get('/', (req, res) => {
  res.render('labeling-tool', { tile: _.sample(tiles), data: "" });
});

app.use('/tiles', Express.static(Path.join(__dirname, 'tiles')))

app.post('/save', (req, res) => {
  console.log('Received label overlay for', req.body.tile,
              `from ${req.body.authorName} <${req.body.authorEmail}>`);

  const overlay = new MapLabelOverlay({
    tile: req.body.tile,
    authorName: req.body.authorName,
    authorEmail: req.body.authorEmail,
    authorIpAddress: req.ip,
    timestamp: new Date(),
    image: req.body.image,
  });

  overlay.save();
  res.send('OK');
});

app.get('/view/:id', async (req, res) => {
  try {
    const overlay = await MapLabelOverlay.findById(req.params.id).exec();
    res.render('labeling-tool', { tile: overlay.tile, data: overlay.image });
  } catch (e) {
    console.error(e);
    res.status(400).send();
  }
});

app.get('/labeled-tiles-list', async (req, res) => {
  try {
    const overlays = await MapLabelOverlay.find({}, {
      tile: true, authorName: true, authorEmail: true, timestamp: true });
    res.render('label-overlay-list', { overlays });
  } catch (e) {
    console.error(e);
    res.status(500).send();
  }
});

Mongoose.connect('mongodb://localhost:27017/openafro', { useNewUrlParser: true }).then(() => {
  app.listen(8000, (err) => {
    if (err) {
      return console.error(err);
    }
    console.log('Listening on port 8000');
  });
});
